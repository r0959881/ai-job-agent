"""Web search: job postings on company career sites, found through the Brave Search API.

A plain web search returns listing pages ("120 Data Engineer jobs in Belgium") and
copies of LinkedIn posts, so the search is aimed at the career-site platforms
companies post on (CAREER_SITES), where every page is one posting. Listing pages and
sites another source already reads are still dropped, and a result is kept only when
the page carries schema.org JobPosting data, the markup career sites add for Google Jobs.

When Brave's quota runs out (or no Brave key is set), the search falls back to Groq's
browser_search tool. One Groq search uses about 60,000 tokens of the free tier's
daily limit, so a run makes at most GROQ_SEARCHES_PER_RUN of them, on the small
model, to leave the CV-tailoring model's own limit untouched.
"""
import re
import time
from urllib.parse import urlparse

import requests

import user_scope
from job_sources import Search, SourceUnavailable, or_query, sites

BRAVE_API = "https://api.search.brave.com/res/v1/web/search"
GROQ_MODEL = "openai/gpt-oss-20b"
GROQ_SEARCHES_PER_RUN = 2
TIMEOUT = 30
QUOTA_PAUSE = 3600  # seconds Brave is skipped after it reports an exhausted quota

CAREER_SITES = ("boards.greenhouse.io", "job-boards.greenhouse.io", "jobs.lever.co", "jobs.ashbyhq.com",
                "teamtailor.com", "recruitee.com", "jobs.smartrecruiters.com", "apply.workable.com",
                "jobs.personio.com", "myworkdayjobs.com")
# Sites with their own source (or that block scripts): their results would only be duplicates.
SKIP_DOMAINS = ("linkedin.", "indeed.", "glassdoor.", "stepstone.", "jobat.be", "vdab.be", "michaelpage.",
                "randstad.", "tempo-team.", "manpower.", "hays.", "roberthalf.", "actiris.", "leforem.", "adzuna.",
                "vacature.com", "remotive.", "himalayas.", "jobicy.", "remoteok.", "arbeitnow.")
_LISTING = re.compile(r"\b\d[\d.,]*\+?\s+(?:\w+\s+){0,4}(?:jobs|vacatures|vacancies|emplois|offres|stellen)\b"
                      r"|\b(?:jobs|vacatures|emplois|offres d'emploi) (?:in|en|à)\b|\bjob search\b|\bsalary\b", re.I)
_URL = re.compile(r"https?://[^\s|)\]>【】\"']+")

_brave_paused_until = 0.0


class QuotaExceeded(SourceUnavailable):
    pass


def _freshness(window_hours):
    return "pd" if window_hours <= 24 else "pw" if window_hours <= 24 * 7 else "pm"


def brave_search(query, key, window_hours, count=20):
    """[(url, title)] from Brave. Raises QuotaExceeded when the plan's quota or rate limit is spent."""
    response = requests.get(BRAVE_API, headers={"X-Subscription-Token": key, "Accept": "application/json"},
                            params={"q": query, "count": count, "freshness": _freshness(window_hours)},
                            timeout=TIMEOUT)
    if response.status_code in (402, 429):
        raise QuotaExceeded(f"Brave Search quota reached ({response.status_code})")
    response.raise_for_status()
    results = (response.json().get("web") or {}).get("results") or []
    return [(item.get("url", ""), sites.plain_text(item.get("title"))) for item in results if item.get("url")]


def groq_search(query, keys, window_hours):
    """[(url, title)] from Groq's browser_search tool (the fallback), switching keys at a key's limit."""
    from tailor import get_client

    days = max(1, -(-window_hours // 24))
    query = query.split(" (site:")[0]  # Brave's site filters mean nothing to Groq
    prompt = (f"Search the web for current job postings for: {query}, posted in the last {days} days. "
              "Only individual job ads on company career pages or job sites, not search result or listing pages, "
              "and not on LinkedIn, Indeed, Glassdoor, StepStone or Jobat. "
              "Answer with one line per posting: URL | job title | company. Plain URLs, no citations. "
              "At most 10 lines, nothing else.")
    response = get_client(keys).chat.completions.create(
        model=GROQ_MODEL, messages=[{"role": "user", "content": prompt}], tools=[{"type": "browser_search"}],
        tool_choice="required", reasoning_effort="low", max_completion_tokens=2000)
    found = []
    for line in (response.choices[0].message.content or "").splitlines():
        match = _URL.search(line)
        if match:
            parts = [part.strip(" *`") for part in line[match.end():].split("|") if part.strip(" *`")]
            found.append((match.group(0).rstrip(".,;"), parts[0] if parts else ""))
    return found


def is_candidate(url, title):
    """Whether a result could be a single posting on a site no other source reads."""
    host = urlparse(url).netloc.lower()
    if not host or any(domain in host for domain in SKIP_DOMAINS):
        return False
    return not _LISTING.search(title or "") and not re.search(r"[?&](q|query|keywords?|search)=", url, re.I)


class Engine:
    """Brave first, Groq when Brave is out of quota; shared by one run's searches."""

    def __init__(self, brave_key, groq_keys):
        self.brave_key, self.groq_keys = brave_key, groq_keys
        self.groq_left = GROQ_SEARCHES_PER_RUN

    def search(self, query, window_hours):
        """(results, engine name)."""
        global _brave_paused_until
        if self.brave_key and time.monotonic() >= _brave_paused_until:
            try:
                return brave_search(query, self.brave_key, window_hours), "Brave"
            except QuotaExceeded:
                _brave_paused_until = time.monotonic() + QUOTA_PAUSE
                if not self.groq_keys:
                    raise
        if not self.groq_keys:
            if self.brave_key:  # Brave is paused after an exhausted quota
                raise QuotaExceeded("Brave Search quota reached; add a Groq key to fall back on.")
            raise RuntimeError("Add a Brave Search or Groq API key in Settings → Integrations.")
        if self.groq_left <= 0:
            return [], "Groq"  # this run's Groq searches are used up: skip quietly
        self.groq_left -= 1
        return groq_search(query, self.groq_keys, window_hours), "Groq"


def located(item, region):
    """Whether a posting is in the searched region. Web results are not limited to one country,
    so unlike the site adapters the region is checked here, never assumed."""
    text = (item.get("location") or "").lower()
    return any(re.search(rf"\b{re.escape(marker)}\b", text) for marker in region["markers"])


def _details(url):
    """The page's JobPosting as an item, or None when the page is not a single posting."""
    posting = sites.job_posting(sites._get(url, browser=True))
    return sites.posting_item(posting, url) if posting else None


def fetch(query, ctx, region, engine, cache):
    results, _engine = engine.search(query, ctx.window_hours)
    jobs = []
    for url, title in results:
        url = re.sub(r"/apply/?$", "", url)  # Lever's apply form; the posting is one level up
        if not is_candidate(url, title) or (title and sites._excluded(title, ctx)):
            continue
        item = cache.get(url, lambda url=url: _details(url))
        if not item or not item["title"] or sites._excluded(item["title"], ctx) or not located(item, region):
            continue
        jobs.append(item)
        if len(jobs) >= ctx.results_per_search:
            break
    return jobs


def _groq_keys():
    from tailor import groq_keys

    return groq_keys()


def configured():
    return bool(user_scope.secret("BRAVE_API_KEY") or _groq_keys())


def plan(ctx):
    """One search per selected region and role; nothing without a Brave or Groq key."""
    brave_key, groq_keys = user_scope.secret("BRAVE_API_KEY"), _groq_keys()
    if not (brave_key or groq_keys):
        return []
    engine = Engine(brave_key, groq_keys)
    cache = sites.DetailCache(ctx.settings.get("scraping", {}).get("time_budget"))
    searches = []
    for region in ctx.regions:
        place = region["label"] if region in ctx.countries else "remote"
        for role, phrases in ctx.role_queries.items():
            phrase = or_query(phrases)
            if not phrase:
                continue
            query = f"({phrase}) {place} (" + " OR ".join(f"site:{site}" for site in CAREER_SITES) + ")"
            searches.append(Search("websearch", "Web search", f"{region['label']} · {role}",
                                   lambda query=query, region=region: fetch(query, ctx, region, engine, cache),
                                   region, {"role": role, "region": region["id"]}))
    return searches
