"""Job sites read from their own search pages: StepStone, VDAB, Michael Page, Jobat, the
staffing agencies (Randstad, Manpower, Hays, Robert Half) and the public employment
services of Brussels (Actiris) and Wallonia (Le Forem).

None of them has a public API, so each adapter reads what the site's own web
page uses: StepStone's embedded result JSON, VDAB's and Actiris's search services,
Le Forem's open-data feed, and the HTML (with schema.org JobPosting data where the
site has it) of the others. Jobat and the agencies refuse plain HTTP clients, so they
are read with curl_cffi's Chrome fingerprint. Detail pages are only fetched for
results the relevance gate could keep, once per run.

Tempo-Team now redirects to Randstad and Vacature to Jobat, so those brands are covered.
"""
import json
import re
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from job_sources import (USER_AGENT, Search, SourceUnavailable, covered_regions, in_region, is_fresh, plain_text,
                         timestamp)

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
RANDSTAD = "https://www.randstad.be"
MANPOWER = "https://www.manpower.be"
HAYS = "https://www.hays.be"
ROBERT_HALF = "https://www.roberthalf.com"
ACTIRIS = "https://www.actiris.brussels"
FOREM_API = "https://www.odwb.be/api/explore/v2.1/catalog/datasets/offres-d-emploi-forem/records"

_STEPSTONE_STATE = re.compile(r'window\.__PRELOADED_STATE__\["app-unifiedResultlist"\]\s*=\s*(\{.*?\});\s*\n', re.S)
_JSON_LD = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S)


RETRY_PAUSE = 3  # seconds before the one retry of a request that timed out or lost its connection


def _get(url, params=None, browser=False):
    """A page's HTML. `browser` sends Chrome's TLS fingerprint, for sites that refuse plain HTTP clients.

    A site that does not answer once (Randstad sometimes sends nothing for 30 seconds) gets one
    more try, so a single slow answer does not cost the whole search.
    """
    from curl_cffi.requests import exceptions as browser_errors

    transient = (requests.Timeout, requests.ConnectionError, browser_errors.Timeout, browser_errors.ConnectionError)
    for attempt in (1, 2):
        try:
            if browser:
                from curl_cffi import requests as browser_requests

                response = browser_requests.get(url, params=params, impersonate="chrome", timeout=TIMEOUT)
            else:
                response = requests.get(url, params=params, headers=BROWSER_HEADERS, timeout=TIMEOUT)
        except transient:
            if attempt == 2:
                raise
            time.sleep(RETRY_PAUSE)
            continue
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


# --- Detail pages shared by the agencies and web search --------------------------------------

def posting_item(posting, url, region=None):
    """A schema.org JobPosting as a normalised item."""
    places = posting.get("jobLocation") or {}
    place = places[0] if isinstance(places, list) and places else places
    address = (place.get("address") if isinstance(place, dict) else None) or {}
    if isinstance(address, str):
        address = {"addressLocality": address}
    location = ", ".join(dict.fromkeys(filter(None, [address.get("addressLocality"), address.get("addressRegion")])))
    if str(posting.get("jobLocationType") or "").upper() == "TELECOMMUTE":
        location = f"{location} (Remote)".strip()
    organisation = posting.get("hiringOrganization") or {}
    parts = [plain_text(posting.get(key)) for key in ("description", "responsibilities", "qualifications", "skills")]
    employment = posting.get("employmentType")
    return {
        "title": plain_text(posting.get("title")),
        "company_name": organisation.get("name", "") if isinstance(organisation, dict) else str(organisation),
        "description": "\n\n".join(dict.fromkeys(part for part in parts if part)),
        "location": in_region(location, region),
        "url": url,
        "created": posting.get("datePosted", ""),
        "contract_type": ", ".join(employment) if isinstance(employment, list) else str(employment or ""),
    }


def page_details(url):
    """A job page as an item: its JobPosting data, or else its heading and main text."""
    page = _get(url, browser=True)
    posting = job_posting(page)
    if posting:
        return posting_item(posting, url)
    soup = BeautifulSoup(page, "html.parser")
    for node in soup.select("script, style, noscript, header, footer, nav, form"):
        node.decompose()
    heading = soup.find("h1")
    meta = soup.find("meta", attrs={"name": "description"})
    main = soup.select_one("main") or soup.body or soup
    text = "\n\n".join(filter(None, [meta.get("content", "") if meta else "", main.get_text("\n", strip=True)]))
    return {"title": heading.get_text(" ", strip=True) if heading else "", "description": text[:8000]}


# A vacancy page that says the job is gone ("helaas, deze vacature is afgesloten").
_CLOSED = re.compile(r"afgesloten|niet meer beschikbaar|no longer available|n'est plus disponible|has expired|"
                     r"vacature is verlopen|offre (?:a )?expir", re.I)
OLDER_IN_A_ROW = 3  # newest-first lists: stop after this many postings older than the run's window


def _detail_jobs(links, company, ctx, region, cache, newest_first=False):
    """Items for detail-page links: (url, title from the result list or '').

    With `newest_first` the links are ordered newest first, so reading stops once postings fall
    outside the run's window instead of opening every result.
    """
    jobs, older = [], 0
    for url, title in links:
        job = {"title": title, "company_name": company, "description": "", "location": in_region("", region),
               "url": url, "created": ""}
        if not (title and _excluded(title, ctx)):
            detail = cache.get(url, lambda url=url: page_details(url))
            if detail:
                job.update({key: value for key, value in detail.items() if value})
                job["location"] = in_region(job["location"], region)
        if newest_first and job["created"]:
            older = 0 if is_fresh(job, ctx.cutoff) else older + 1
            if older >= OLDER_IN_A_ROW:
                break
        if job["title"] and not _CLOSED.search(job["title"]) and not _excluded(job["title"], ctx):
            jobs.append(job)
        if len(jobs) >= ctx.results_per_search:
            break
    return jobs


def _by_number(links):
    """Links ending in the site's job number, highest (newest) first: the sites list by relevance only."""
    return sorted(links, key=lambda url: int(re.search(r"(\d+)$", url).group(1)), reverse=True)


def _links(page, base, pattern):
    """Distinct absolute links matching `pattern`, without query strings, in page order."""
    found = re.findall(pattern, page)
    return list(dict.fromkeys(urljoin(base, link.split("?")[0]) for link in found))


# --- Staffing agencies ----------------------------------------------------------------------

RANDSTAD_SITEMAPS = (f"{RANDSTAD}/sitemaps/jobs/nl/sitemap-jobdetails.xml",
                     f"{RANDSTAD}/sitemaps/jobs/fr/sitemap-jobdetails.xml")
SITEMAP_CACHE_SECONDS = 600
_randstad_sitemap = {"at": 0.0, "jobs": {}}  # job url -> last modified (ISO)


def randstad_recent(ctx):
    """Randstad job links changed within the run's window, from its sitemaps (about 1,500 jobs with dates).

    Its search lists by relevance and its result cards carry no date, so the sitemap is the way
    to find today's jobs. It is read once and kept a few minutes (each web-app search is its own request).
    """
    if time.monotonic() - _randstad_sitemap["at"] > SITEMAP_CACHE_SECONDS:
        jobs = {}
        for url in RANDSTAD_SITEMAPS:
            try:
                xml = _get(url, browser=True)
            except Exception:  # curl_cffi's errors; a missing language sitemap only costs its jobs
                continue
            for loc, modified in re.findall(r"<loc>([^<]+)</loc>\s*<lastmod>([^<]+)</lastmod>", xml):
                jobs[loc.strip()] = modified.strip()
        _randstad_sitemap.update(at=time.monotonic(), jobs=jobs)
    since = ctx.cutoff
    return {url for url, modified in _randstad_sitemap["jobs"].items()
            if (timestamp(modified) or 0) >= since}


def fetch_randstad(query, ctx, region, cache):
    """Randstad (and Tempo-Team, which redirects to it): today's jobs from its sitemap, then their JobPosting data.

    A job counts for the search when the site's own search lists it, or when the search words are
    in its title (the link starts with it: /werknemers/jobs/junior-data-analyst_mechelen_<id>/).
    """
    recent = randstad_recent(ctx)
    page = _get(f"{RANDSTAD}/werknemers/jobs/q-{slug(query)}/", browser=True)
    listed = _links(page, RANDSTAD, r'href="(/werknemers/jobs/[a-z0-9-]+_[a-z0-9-]+_[0-9a-f-]{36}/)"')
    words = slug(query).split("-")
    titled = [url for url in sorted(recent)
              if all(word in url.split("/werknemers/jobs/")[-1].split("_")[0].split("-") for word in words)]
    links = list(dict.fromkeys([url for url in listed if url in recent] + titled))
    return _detail_jobs([(url, "") for url in links], "Randstad", ctx, region, cache)


def fetch_manpower(query, ctx, region, cache):
    """Manpower: every result page, newest job number first (its pages list by relevance)."""
    links = []
    for page_number in (1, 2, 3):
        page = _get(f"{MANPOWER}/nl/vacatures", {"query": query, "page": page_number}, browser=True)
        found = _links(page, MANPOWER, r'href="(/nl/vacature/[a-z0-9-]+-\d+)"')
        if not found:
            break
        links += found
    return _detail_jobs([(url, "") for url in _by_number(dict.fromkeys(links))], "Manpower", ctx, region, cache,
                        newest_first=True)


def fetch_hays(query, ctx, region, cache):
    """Hays: every result (about ten). Its job numbers do not follow the posting date, so all are read."""
    page = _get(f"{HAYS}/en/job-search/{slug(query)}-jobs", browser=True)
    links = _links(page, HAYS, r'href="([^"]*/job-detail/[^"]+_\d+)[?"]')
    return _detail_jobs([(url, "") for url in links], "Hays", ctx, region, cache)


def _js_unescape(match):
    code = match.group(1)
    if code[0] in "xu":
        return chr(int(code[1:], 16))
    return {"n": "\n", "t": "\t", "r": "\r"}.get(code, code)


def robert_half_jobs(page):
    """The search results Robert Half embeds in its page: a JSON list inside a JavaScript string."""
    start = page.find("\\x22jobs\\x22:[")
    if start < 0:
        if "\\x22found\\x22:\\x220\\x22" in page:  # a search without results has no job list at all
            return []
        raise ValueError("Robert Half changed its result page (no embedded job list found).")
    escaped = page[start:start + 3_000_000]
    text = re.sub(r"\\(x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|.)", _js_unescape, escaped[escaped.find("["):])
    jobs, _end = json.JSONDecoder().raw_decode(text)
    return [job for job in jobs if isinstance(job, dict)]


def fetch_robert_half(query, ctx, region, _cache=None):
    """Robert Half: its page embeds every result with date, city and full description, so no page is opened."""
    page = _get(f"{ROBERT_HALF}/be/en/jobs/all/{slug(query)}", browser=True)
    jobs = []
    for job in robert_half_jobs(page):
        title = plain_text(job.get("jobtitle"))
        if not title or _excluded(title, ctx):
            continue
        jobs.append({
            "title": title, "company_name": "Robert Half",
            "description": plain_text(job.get("description")),
            "location": in_region(job.get("city") or "", region),
            "url": job.get("job_detail_url") or "",
            "created": job.get("date_posted") or "",
            "contract_type": job.get("emptype") or "",
        })
    jobs.sort(key=lambda job: job["created"], reverse=True)
    return jobs[:ctx.results_per_search]


# --- Public employment services: Actiris (Brussels) and Le Forem (Wallonia) ----------------

def fetch_actiris(query, ctx, region, _cache=None):
    """Actiris's own search service. Its offers list title, contract and postcode, not the full text."""
    body = {"offreFilter": {"texte": query}, "pageOption": {"page": 1, "pageSize": min(ctx.results_per_search, 50)},
            "searchParams": {}}
    from curl_cffi import requests as browser_requests

    response = browser_requests.post(f"{ACTIRIS}/api/Offer/GetAllOffers", json=body, headers={"Accept-Language": "nl"},
                                     impersonate="chrome", timeout=TIMEOUT)
    response.raise_for_status()
    jobs = []
    for offer in response.json().get("offers") or []:
        title = offer.get("titreNl") or offer.get("titreFr") or ""
        if not title or not offer.get("reference"):
            continue
        place = " ".join(filter(None, [offer.get("codePostal"), offer.get("communeNl") or offer.get("communeFr")]))
        contract = offer.get("typeContratLibelle") or offer.get("typeContrat") or ""
        jobs.append({
            "title": title, "company_name": offer.get("employer") or "Via Actiris",
            "description": "\n".join(filter(None, [title, f"Contract: {contract}" if contract else ""])),
            "location": in_region(place, region),
            "url": f"{ACTIRIS}/nl/burgers/jobadvertentie/?reference={offer['reference']}&type={offer.get('typeOffer', '')}",
            "created": offer.get("dateCreation", ""), "contract_type": contract,
        })
    return jobs


FOREM_CACHE_SECONDS = 600
FOREM_RETRIES = 3
_forem_feeds = {}  # where clause -> (fetched at, offers)
_forem_quota = {"reset": None}  # when the portal's daily quota for anonymous users is spent: its reset time


class ForemQuotaReached(SourceUnavailable):
    pass


def _forem_reset_text(reset):
    return reset.astimezone().strftime("%H:%M") if reset else "midnight UTC"


def _forem_get(params):
    """One portal request, waiting and retrying when it answers 429 for a burst of requests.

    The portal also allows 10,000 anonymous requests a day (counted per network, so a shared
    connection can spend it). Once that is spent no request is sent until it resets.
    """
    reset = _forem_quota["reset"]
    if reset and datetime.now(UTC) < reset:
        raise ForemQuotaReached(f"Le Forem's daily limit is reached; it resets at {_forem_reset_text(reset)}.")
    for attempt in range(FOREM_RETRIES + 1):
        response = requests.get(FOREM_API, params=params, headers=BROWSER_HEADERS, timeout=TIMEOUT)
        if response.status_code == 429:
            try:
                body = response.json()
            except ValueError:
                body = {}
            if isinstance(body, dict) and body.get("reset_time"):  # the daily quota, not a burst
                reset = datetime.fromisoformat(body["reset_time"].replace("Z", "+00:00"))
                _forem_quota["reset"] = reset
                raise ForemQuotaReached(f"Le Forem's open-data portal allows {body.get('call_limit', 10000)} "
                                        f"requests a day and that limit is reached; it resets at "
                                        f"{_forem_reset_text(reset)}.")
        if response.status_code != 429 or attempt == FOREM_RETRIES:
            response.raise_for_status()
            return response.json().get("results") or []
        wait = response.headers.get("Retry-After", "")
        time.sleep(min(float(wait) if wait.replace(".", "", 1).isdigit() else 2.0 * 2 ** attempt, 30))
    return []


def forem_offers(ctx):
    """The recent offers matching any of the run's search phrases, fetched once and shared by its searches.

    One request per phrase made the portal answer "429 Too Many Requests", so the run's phrases go
    into one query. The result is kept for a few minutes, because the web app sends each search of a
    run as its own request.
    """
    since = (datetime.now(UTC) - timedelta(days=_age_days(ctx))).date().isoformat()
    phrases = " OR ".join(f'search("{query.replace(chr(34), "")}")' for query in ctx.queries())
    where = f"({phrases}) AND datedebutdiffusion >= date'{since}'"
    fetched_at, offers = _forem_feeds.get(where, (0.0, None))
    if offers is None or time.monotonic() - fetched_at > FOREM_CACHE_SECONDS:
        offers = _forem_get({"where": where, "order_by": "datedebutdiffusion desc", "limit": 100})
        _forem_feeds[where] = (time.monotonic(), offers)
    return offers


def _forem_phrase(offer, phrases):
    """The search phrase an offer belongs to: the one sharing most words with it, else the first.

    The portal's search also matches translations ("Analyste de données" for "data analyst"), so
    every offer it returned is kept; this only decides which of the run's searches reports it.
    """
    text = " ".join(str(offer.get(key) or "") for key in ("titreoffre", "metier")).lower()
    overlap = [sum(word in text for word in re.findall(r"\w+", phrase.lower())) for phrase in phrases]
    return phrases[overlap.index(max(overlap))] if phrases else ""


def fetch_forem(query, ctx, region, _cache=None):
    """Le Forem's job offers, from the Walloon open-data portal (updated daily)."""
    phrases = ctx.queries()
    mine = [offer for offer in forem_offers(ctx) if _forem_phrase(offer, phrases) == query]
    jobs = []
    for offer in mine[:ctx.results_per_search]:
        details = [
            ("Occupation", offer.get("metier")), ("Contract", offer.get("typecontrat")),
            ("Working hours", offer.get("regimetravail")), ("Experience", offer.get("experiencerequise")),
            ("Education", ", ".join(offer.get("niveauxetudes") or [])),
            ("Required languages", ", ".join(offer.get("langues") or [])),
            ("Sector", ", ".join(offer.get("secteurs") or [])),
        ]
        jobs.append({
            "title": offer.get("titreoffre", ""), "company_name": offer.get("nomemployeur") or "Via Le Forem",
            "description": "\n".join(f"{label}: {value}" for label, value in details if value),
            "location": in_region(", ".join((offer.get("lieuxtravaillocalite") or [])[:2]), region),
            "url": offer.get("url") or f"https://www.leforem.be/recherche-offres/offre-detail/{offer.get('numerooffreforem')}",
            "created": offer.get("datedebutdiffusion", ""), "contract_type": offer.get("typecontrat") or "",
        })
    return jobs


# --- Planning ------------------------------------------------------------------------------

NAMES = {"stepstone": "StepStone", "vdab": "VDAB", "michaelpage": "Michael Page", "jobat": "Jobat",
         "randstad": "Randstad", "manpower": "Manpower", "hays": "Hays", "roberthalf": "Robert Half",
         "actiris": "Actiris", "forem": "Le Forem"}
FETCHERS = {"stepstone": fetch_stepstone, "vdab": fetch_vdab, "michaelpage": fetch_michael_page, "jobat": fetch_jobat,
            "randstad": fetch_randstad, "manpower": fetch_manpower, "hays": fetch_hays,
            "roberthalf": fetch_robert_half, "actiris": fetch_actiris, "forem": fetch_forem}


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
