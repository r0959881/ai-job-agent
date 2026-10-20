"""Job sources beyond Gmail alerts: web scrapers, job sites, public job APIs and company career boards.

Every source turns a search context into a list of `Search` units. discovery.py
runs them one by one (so progress and cancellation work per search) and stores
the normalised items through the same relevance gate as every other source.

A normalised item has the keys save_jobs_to_db reads: title, company_name,
description, location, url, created (ISO date), plus optional salary fields.
"""
import html
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

import regions as region_catalog

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0 Safari/537.36"
)
COMPANY_BOARD_ATS = ("greenhouse", "lever", "ashby", "recruitee", "smartrecruiters")


@dataclass
class Search:
    source: str  # registry key, e.g. "linkedin"
    name: str  # stored in jobs.source, e.g. "LinkedIn"
    label: str  # shown in progress, e.g. "Belgium · Data Analyst"
    fetch: Callable[[], list]
    region: dict | None = None  # set when the source already searched inside this region
    data: dict = field(default_factory=dict)


@dataclass
class Context:
    regions: list  # region dicts from regions.py
    role_queries: dict  # role name -> list of search phrases
    window_hours: int
    settings: dict

    @property
    def cutoff(self):
        return datetime.now(UTC).timestamp() - self.window_hours * 3600

    @property
    def countries(self):
        return [region for region in self.regions if region["id"] != region_catalog.REMOTE]

    @property
    def wants_remote(self):
        return any(region["id"] == region_catalog.REMOTE for region in self.regions)

    def queries(self):
        """Distinct search phrases across the selected roles, in order."""
        seen, result = set(), []
        for phrases in self.role_queries.values():
            for phrase in phrases:
                if phrase.lower() not in seen:
                    seen.add(phrase.lower())
                    result.append(phrase)
        return result

    @property
    def results_per_search(self):
        return int(self.settings.get("scraping", {}).get("results_per_search", 25))


# The catalogue the UI shows. `covers(region)` says whether a source can search a region.
SOURCES = {
    "linkedin": {
        "label": "LinkedIn", "kind": "scraper", "default": True,
        "description": "Public LinkedIn job search (no login). Full descriptions are fetched, so it is slower.",
        "covers": lambda region: True,
    },
    "indeed": {
        "label": "Indeed", "kind": "scraper", "default": True,
        "description": "Indeed's country sites, with full descriptions. Fast and broad.",
        "covers": lambda region: bool(region["indeed"]),
    },
    "glassdoor": {
        "label": "Glassdoor", "kind": "scraper", "default": False,
        "description": "Glassdoor search. Often blocks automated requests, so it is off by default.",
        "covers": lambda region: region["glassdoor"],
    },
    "stepstone": {
        "label": "StepStone", "kind": "scraper", "default": True,
        "description": "StepStone Belgium and Germany. Uses the search snippet, as detail pages block scripts.",
        "covers": lambda region: region["id"] in {"BE", "DE"},
    },
    "jobat": {
        "label": "Jobat", "kind": "scraper", "default": True,
        "description": "Belgium's Jobat job site, with full descriptions.",
        "covers": lambda region: region["id"] == "BE",
    },
    "michaelpage": {
        "label": "Michael Page", "kind": "scraper", "default": True,
        "description": "Recruiter Michael Page in Belgium/Luxembourg, Germany, France, the UK, Ireland, "
                       "Switzerland, Spain, Italy, Poland and Portugal.",
        "covers": lambda region: region["id"] in {"BE", "LU", "DE", "FR", "GB", "IE", "CH", "ES", "IT", "PL", "PT"},
    },
    "adzuna": {
        "label": "Adzuna", "kind": "api", "default": True, "requires": ["ADZUNA_APP_ID", "ADZUNA_APP_KEY"],
        "description": "Job aggregator API for 19 countries. Needs a free API key.",
        "covers": lambda region: bool(region["adzuna"]),
    },
    "arbeitnow": {
        "label": "Arbeitnow", "kind": "api", "default": True,
        "description": "Public job board, mostly Germany plus remote roles.",
        "covers": lambda region: region["id"] in {"DE", "AT", "CH", region_catalog.REMOTE},
    },
    "arbeitsagentur": {
        "label": "Bundesagentur für Arbeit", "kind": "api", "default": True,
        "description": "Germany's federal job exchange (Jobbörse), the largest German job database.",
        "covers": lambda region: region["id"] == "DE",
    },
    "vdab": {
        "label": "VDAB", "kind": "api", "default": True,
        "description": "Flanders' public employment service, with full descriptions and required languages.",
        "covers": lambda region: region["id"] == "BE",
    },
    "jobtech": {
        "label": "Arbetsförmedlingen", "kind": "api", "default": True,
        "description": "Sweden's public employment service (JobTech open API).",
        "covers": lambda region: region["id"] == "SE",
    },
    "remotive": {
        "label": "Remotive", "kind": "api", "default": True, "description": "Remote jobs board.",
        "covers": lambda region: region["id"] == region_catalog.REMOTE,
    },
    "himalayas": {
        "label": "Himalayas", "kind": "api", "default": True, "description": "Remote jobs board.",
        "covers": lambda region: region["id"] == region_catalog.REMOTE,
    },
    "jobicy": {
        "label": "Jobicy", "kind": "api", "default": True, "description": "Remote jobs board.",
        "covers": lambda region: region["id"] == region_catalog.REMOTE,
    },
    "remoteok": {
        "label": "Remote OK", "kind": "api", "default": True, "description": "Remote jobs board.",
        "covers": lambda region: region["id"] == region_catalog.REMOTE,
    },
    "company_boards": {
        "label": "Company career pages", "kind": "api", "default": True,
        "description": "Companies you follow on Greenhouse, Lever, Ashby, Recruitee or SmartRecruiters. "
                       "Add them in Settings → Search.",
        "covers": lambda region: True,
    },
    "gmail": {
        "label": "Gmail alerts", "kind": "email", "default": True,
        "description": "LinkedIn, Indeed, StepStone, VDAB… alert emails in your inbox.",
        "covers": lambda region: True,
    },
}
SOURCE_KEYS = list(SOURCES)
# Sources discovery.py runs itself (Adzuna keeps its own step, Gmail lives in gmail_parser).
SCRAPERS = [key for key, source in SOURCES.items() if source["kind"] == "scraper"]
BOARDS = [key for key, source in SOURCES.items() if source["kind"] == "api" and key != "adzuna"]


def covers(source_key, region) -> bool:
    check: Callable[[dict], bool] = SOURCES[source_key]["covers"]  # type: ignore[assignment]
    return bool(check(region))


def covered_regions(source_key, region_list):
    return [region for region in region_list if covers(source_key, region)]


def plain_text(raw):
    """HTML (possibly entity-escaped) to plain text with collapsed whitespace."""
    text = html.unescape(html.unescape(str(raw or "")))
    text = re.sub(r"<(br|/p|/li|/h\d)[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\n\s*\n+", "\n", text)).strip()


def to_iso(value):
    """Epoch seconds/ms, date, datetime or ISO-like text to an ISO string ('' if unknown)."""
    if value in (None, ""):
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    text = str(value).strip()
    if re.fullmatch(r"\d{9,13}", text):
        number = int(text)
        return datetime.fromtimestamp(number / 1000 if number > 10**11 else number, UTC).isoformat()
    return text.replace(" UTC", "+00:00")


def timestamp(value):
    text = to_iso(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)).timestamp()


def is_fresh(item, cutoff):
    """Keep undated items; drop dated ones older than the cutoff."""
    posted = timestamp(item.get("created"))
    return posted is None or posted >= cutoff


def in_region(location, region):
    """Make sure a result from a region-scoped search names that region in its location.

    Sources such as Indeed Belgium only return Belgian jobs, but their location
    text can be a bare town ("Malines") that the relevance gate does not know.
    """
    if not region or region["id"] == region_catalog.REMOTE:
        return location
    text = (location or "").lower()
    if any(re.search(rf"\b{re.escape(marker)}\b", text) for marker in region["markers"]):
        return location
    return f"{location}, {region['label']}" if location else region["label"]


def or_query(phrases):
    """One boolean search for several phrases: "data engineer" OR "data platform"."""
    phrases = [phrase.strip() for phrase in phrases if phrase.strip()]
    if len(phrases) == 1:
        return phrases[0]
    return " OR ".join(f'"{phrase}"' for phrase in phrases)


def plan(source_key, ctx):
    """The searches one source would run for this context."""
    from job_sources import boards, scrapers, sites

    if source_key in sites.NAMES:
        return sites.plan(source_key, ctx)
    if source_key in SCRAPERS:
        return scrapers.plan(source_key, ctx)
    return boards.plan(source_key, ctx)
