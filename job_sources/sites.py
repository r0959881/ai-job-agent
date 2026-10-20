"""Job sites read from their own search pages: StepStone, VDAB, Michael Page and Jobat.

None of them has a public API, so each adapter reads what the site's own web
page uses: StepStone's embedded result JSON, VDAB's search service, and the
HTML (with schema.org JobPosting data) of Michael Page and Jobat. Jobat refuses
plain HTTP clients, so it is read with curl_cffi's Chrome fingerprint. Detail pages
are only fetched for results the relevance gate could keep, once per run.
"""
import json
import re
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from job_sources import USER_AGENT, Search, covered_regions, in_region, plain_text

TIMEOUT = 30
DETAIL_PAUSE = 0.3  # seconds between detail pages, to stay polite
BROWSER_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en,nl;q=0.9,fr;q=0.8,de;q=0.7",
}

# Country sites per region id.
STEPSTONE_SITES = {"BE": "https://www.stepstone.be", "DE": "https://www.stepstone.de"}
MICHAEL_PAGE_SITES = {
    "BE": "https://www.michaelpage.be", "LU": "https://www.michaelpage.be", "DE": "https://www.michaelpage.de",
    "FR": "https://www.michaelpage.fr", "GB": "https://www.michaelpage.co.uk", "IE": "https://www.michaelpage.ie",
    "CH": "https://www.michaelpage.ch", "ES": "https://www.michaelpage.es", "IT": "https://www.michaelpage.it",
    "PL": "https://www.michaelpage.pl", "PT": "https://www.michaelpage.pt",
}
VDAB_API = "https://www.vdab.be/rest/vindeenjob/v4"
# The public key the VDAB web app itself sends with every search.
VDAB_HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json", "Content-Type": "application/json",
                "vej-key-monitor": "b277002f-e1fa-4fc5-868a-fdab633c3851"}
JOBAT = "https://www.jobat.be"

_STEPSTONE_STATE = re.compile(r'window\.__PRELOADED_STATE__\["app-unifiedResultlist"\]\s*=\s*(\{.*?\});\s*\n', re.S)
_JSON_LD = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S)


def _get(url, params=None, browser=False):
    """A page's HTML. `browser` sends Chrome's TLS fingerprint, for sites that refuse plain HTTP clients."""
    if browser:
        from curl_cffi import requests as browser_requests

        response = browser_requests.get(url, params=params, impersonate="chrome", timeout=TIMEOUT)
    else:
        response = requests.get(url, params=params, headers=BROWSER_HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    return response.text


def slug(query):
    """'Data Engineer' -> 'data-engineer', the path form the sites use for a search."""
    return re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")


def _excluded(title, ctx):
    words = [word.lower() for word in ctx.settings.get("exclude_title_keywords", [])]
    return any(re.search(rf"\b{re.escape(word)}\b", (title or "").lower()) for word in words)


def _age_days(ctx):
    return max(1, -(-ctx.window_hours // 24))


class DetailCache:
    """Detail pages fetched during one run, so a job found by two searches is read once.

    With a time budget (the web server sets one), detail pages stop being fetched
    once it is spent, so a search request ends before the host's request timeout.
    """

    def __init__(self, budget=None):
        self.pages = {}
        self.deadline = time.monotonic() + budget if budget else None

    def get(self, key, fetch):
        if key not in self.pages:
            if self.deadline is not None and time.monotonic() > self.deadline:
                return None  # out of time: keep the result with its search-page text only
            try:
                self.pages[key] = fetch()
            except Exception:  # a missing detail page only costs the description
                self.pages[key] = None
            time.sleep(DETAIL_PAUSE)
        return self.pages[key]


def job_posting(page_html):
    """The schema.org JobPosting embedded as JSON-LD, or {}."""
    for block in _JSON_LD.findall(page_html or ""):
        try:
            data = json.loads(block, strict=False)
        except ValueError:
            continue
        for item in data.get("@graph", [data]) if isinstance(data, dict) else data:
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                return item
    return {}


# --- StepStone --------------------------------------------------------------------------

def fetch_stepstone(query, ctx, region, _cache=None):
    """StepStone embeds the result list as JSON. Its detail pages block scripts, so the snippet is kept."""
    params = {"ag": f"age_{min(_age_days(ctx), 30)}", "sort": 2}
    page = _get(f"{STEPSTONE_SITES[region['id']]}/jobs/{slug(query)}", params=params)
    match = _STEPSTONE_STATE.search(page)
    if not match:
        raise ValueError("StepStone changed its result page (no result data found).")
    items = (json.loads(match.group(1)).get("searchResults") or {}).get("items") or []
    jobs = []
    for job in items[: ctx.results_per_search]:
        description = "\n\n".join(filter(None, [plain_text(job.get("textSnippet")),
                                                plain_text(job.get("jobBenefitsHtml"))]))
        jobs.append({
            "title": job.get("title", ""), "company_name": job.get("companyName", ""),
            "description": description, "location": in_region(job.get("location", ""), region),
            "url": (job.get("url") or "").split("?")[0], "created": job.get("datePosted", ""),
        })
    return jobs


# --- VDAB ---------------------------------------------------------------------------------

VDAB_ENTRY_LEVEL = {"1", "2"}  # "Geen ervaring", "Beperkte ervaring"


def _vdab_online_since(ctx):
    if ctx.window_hours <= 48:
        return "1"  # today or yesterday
    if ctx.window_hours <= 24 * 7:
        return "6"  # last week
    return None


def _vdab_details(job_id):
    response = requests.get(f"{VDAB_API}/vacatures/{job_id}", headers=VDAB_HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def vdab_description(detail):
    function = detail.get("functie") or {}
    profile = detail.get("profiel") or {}
    parts = [plain_text((function.get("omschrijving") or {}).get("html")),
             plain_text((profile.get("vereisteKwalificaties") or {}).get("html"))]
    languages = [
        f"{(entry.get('taalCode') or {}).get('label', '')} ({(entry.get('scoreCode') or {}).get('kortLabel', '')})"
        for entry in profile.get("talenKennis") or [] if (entry.get("taalCode") or {}).get("label")
    ]
    if languages:
        parts.append("Required languages: " + ", ".join(languages))
    return "\n\n".join(part for part in parts if part)


def fetch_vdab(query, ctx, region, cache):
    criteria = {"trefwoord": query, "sorteerVeld": "DATUM"}
    since = _vdab_online_since(ctx)
    if since:
        criteria["onlineSindsCode"] = since
    body = {"criteria": criteria, "pagina": 0, "zoekmodus": "C2", "paginaGrootte": min(ctx.results_per_search, 100)}
    response = requests.post(f"{VDAB_API}/vacatureLight/zoek", data=json.dumps(body), headers=VDAB_HEADERS,
                             timeout=TIMEOUT)
    response.raise_for_status()
    jobs = []
    for job in response.json().get("resultaten") or []:
        job_id = (job.get("id") or {}).get("id")
        title = (job.get("vacaturefunctie") or {}).get("naam", "")
        if not job_id:
            continue
        detail = None if _excluded(title, ctx) else cache.get(f"vdab:{job_id}", lambda job_id=job_id: _vdab_details(job_id))
        description = vdab_description(detail) if detail else ""
        experience = job.get("ervaring") or ""
        if experience:
            description += f"\n\nExperience: {experience}"
        competences = ((detail or {}).get("profiel") or {}).get("beroepCompetenties") or []
        codes = {str((entry.get("werkervaring") or {}).get("code")) for entry in competences}
        if codes & VDAB_ENTRY_LEVEL or experience.lower() in {"geen ervaring", "beperkte ervaring"}:
            description += "\nSeniority level: entry level"
        place = (job.get("tewerkstellingsLocatieRegioOfAdres") or "").title()
        jobs.append({
            "title": title, "company_name": job.get("vacatureBedrijfsnaam", ""),
            "description": description.strip(), "location": in_region(place, region),
            "url": f"https://www.vdab.be/vindeenjob/vacatures/{job_id}", "created": job.get("eerstePublicatieDatum", ""),
        })
    return jobs


# --- Michael Page -------------------------------------------------------------------------

def _michael_page_details(url):
    posting = job_posting(_get(url))
    if not posting:
        return None
    address = (posting.get("jobLocation") or {}).get("address") or {}
    return {
        "description": plain_text(posting.get("description")),
        "created": posting.get("datePosted", ""),
        "location": ", ".join(filter(None, [address.get("addressLocality"), address.get("addressRegion")])),
        "company_name": (posting.get("hiringOrganization") or {}).get("name", ""),
    }


def fetch_michael_page(query, ctx, region, cache):
    base = MICHAEL_PAGE_SITES[region["id"]]
    try:
        page = _get(f"{base}/jobs/{slug(query)}")
    except requests.HTTPError as error:
        if error.response is not None and error.response.status_code == 404:
            return []  # Michael Page answers a search without results with 404
        raise
    soup = BeautifulSoup(page, "html.parser")
    jobs = []
    for tile in soup.select("div.job-tile"):
        link = tile.select_one(".job-title a[href]")
        # Tiles linked with ng-src are "people also applied for" suggestions, not search results.
        if not link or "ng-src=" in link["href"]:
            continue
        url = urljoin(base, link["href"].split("?")[0])
        title = link.get_text(" ", strip=True)
        card_text = "\n".join(part.get_text(" ", strip=True) for part in tile.select(".job-summary, .bullet_points"))
        place = (tile.select_one(".job-location") or soup.new_tag("i")).get_text(" ", strip=True)
        job = {"title": title, "company_name": "Michael Page", "description": card_text,
               "location": in_region(place, region), "url": url, "created": ""}
        if not _excluded(title, ctx):
            detail = cache.get(url, lambda url=url: _michael_page_details(url))
            if detail:
                job.update({key: value for key, value in detail.items() if value})
                job["location"] = in_region(job["location"], region)
        jobs.append(job)
        if len(jobs) >= ctx.results_per_search:
            break
    return jobs


# --- Jobat --------------------------------------------------------------------------------

def jobat_posted(label, today=None):
    """'Sinds vandaag' / 'Sinds 3 dagen' / 'Sinds 2 weken' -> ISO date ('' when unknown)."""
    today = today or datetime.now(UTC).date()
    text = (label or "").lower()
    if "vandaag" in text or "aujourd" in text:
        return today.isoformat()
    if "gisteren" in text or "hier" in text:
        return (today - timedelta(days=1)).isoformat()
    match = re.search(r"(\d+)\s*(dag|dagen|jour|jours|week|weken|semaine|semaines|maand|maanden|mois)", text)
    if not match:
        return ""
    number, unit = int(match.group(1)), match.group(2)
    days = number * (7 if unit in {"week", "weken", "semaine", "semaines"}
                     else 30 if unit in {"maand", "maanden", "mois"} else 1)
    return (today - timedelta(days=days)).isoformat()


def _jobat_details(url):
    soup = BeautifulSoup(_get(url, browser=True), "html.parser")
    container = soup.select_one("#jobdetail") or soup

    def prop(name):
        node = container.select_one(f'[itemprop="{name}"]')
        if not node:
            return ""
        return (node.get("content") or node.get_text(" ", strip=True)).strip()

    parts = [prop("description"), prop("qualifications") or prop("skills")]
    return {"description": "\n\n".join(dict.fromkeys(part for part in parts if part)),
            "created": prop("datePosted"), "location": prop("addressLocality")}


def fetch_jobat(query, ctx, region, cache):
    soup = BeautifulSoup(_get(f"{JOBAT}/nl/jobs/results/{slug(query)}", {"orderbyclause": "-jobpublishdate"},
                              browser=True),
                         "html.parser")
    jobs = []
    for card in soup.select("div.jobResults-card"):
        link = card.select_one(".jobTitle a[href]")
        if not link:
            continue
        posted = jobat_posted((card.select_one(".jobCard-duration") or soup.new_tag("i")).get_text(" ", strip=True))
        # Results are newest first, so the first one outside the window ends the search.
        if posted and datetime.fromisoformat(posted).replace(tzinfo=UTC).timestamp() < ctx.cutoff - 86400:
            break
        url = urljoin(JOBAT, link["href"])
        title = link.get_text(" ", strip=True)
        company = (card.select_one(".jobCard-company") or soup.new_tag("i")).get_text(" ", strip=True)
        place = (card.select_one(".jobCard-location") or soup.new_tag("i")).get_text(" ", strip=True)
        job = {"title": title, "company_name": company, "description": "", "location": in_region(place, region),
               "url": url, "created": posted}
        if not _excluded(title, ctx):
            detail = cache.get(url, lambda url=url: _jobat_details(url))
            if detail:
                job["description"] = detail["description"]
                job["created"] = detail["created"] or posted
                job["location"] = in_region(detail["location"] or place, region)
        jobs.append(job)
        if len(jobs) >= ctx.results_per_search:
            break
    return jobs


# --- Planning ------------------------------------------------------------------------------

NAMES = {"stepstone": "StepStone", "vdab": "VDAB", "michaelpage": "Michael Page", "jobat": "Jobat"}
FETCHERS = {"stepstone": fetch_stepstone, "vdab": fetch_vdab, "michaelpage": fetch_michael_page, "jobat": fetch_jobat}


def search(source, query, ctx, region, cache):
    """Run one search on a job site. Tests and the offline demo replace this function."""
    return FETCHERS[source](query, ctx, region, cache)


def plan(source, ctx):
    """One search per covered country and search phrase."""
    if source not in FETCHERS:
        raise ValueError(f"Unknown job site: {source}")
    cache = DetailCache(ctx.settings.get("scraping", {}).get("time_budget"))
    searches = []
    seen_sites = set()
    for region in covered_regions(source, ctx.countries):
        site = MICHAEL_PAGE_SITES.get(region["id"]) if source == "michaelpage" else region["id"]
        if site in seen_sites:  # Belgium and Luxembourg share one Michael Page site
            continue
        seen_sites.add(site)
        searches += [
            Search(source, NAMES[source], f"{region['label']} · {query}",
                   lambda query=query, region=region: search(source, query, ctx, region, cache), region)
            for query in ctx.queries()
        ]
    return searches
