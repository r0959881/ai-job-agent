"""LinkedIn, Indeed and Glassdoor through the open-source JobSpy scraper.

One search per site, region and role: the role's search phrases are combined
into a single boolean query, which keeps the number of requests (and the risk of
being rate limited) low.
"""
import math

from job_sources import Search, covered_regions, in_region, or_query

SITE_NAMES = {"linkedin": "LinkedIn", "indeed": "Indeed", "glassdoor": "Glassdoor"}


class ScraperUnavailable(RuntimeError):
    pass


def _scrape(**kwargs):
    """Call JobSpy and return plain dict rows. Tests replace this function."""
    try:
        from jobspy import scrape_jobs
    except ImportError as error:  # pragma: no cover - depends on the environment
        raise ScraperUnavailable("python-jobspy is not installed. Run: pip install -r requirements.txt") from error
    frame = scrape_jobs(verbose=0, **kwargs)
    return frame.to_dict("records") if frame is not None else []


def _value(row, key):
    value = row.get(key)
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return value


def normalise(row, region):
    description = str(_value(row, "description") or "")
    level = _value(row, "job_level")
    if level:
        description = f"{description}\n\nSeniority level: {level}".strip()
    location = str(_value(row, "location") or "")
    if _value(row, "is_remote") and "remote" not in location.lower():
        location = f"{location} (Remote)".strip()
    interval = _value(row, "interval")
    return {
        "title": str(_value(row, "title") or ""),
        "company_name": str(_value(row, "company") or "Unknown"),
        "description": description,
        "location": in_region(location, region),
        "url": str(_value(row, "job_url_direct") or _value(row, "job_url") or ""),
        "created": _value(row, "date_posted") or "",
        "contract_type": str(_value(row, "job_type") or ""),
        "salary_min": _value(row, "min_amount") if interval in (None, "yearly") else None,
        "salary_max": _value(row, "max_amount") if interval in (None, "yearly") else None,
        "salary_currency": str(_value(row, "currency") or ""),
    }


def _kwargs(site, region, query, ctx):
    scraping = ctx.settings.get("scraping", {})
    kwargs = {
        "site_name": [site],
        "search_term": query,
        "results_wanted": ctx.results_per_search,
        "hours_old": ctx.window_hours,
    }
    if region["id"] == "REMOTE":
        kwargs.update(location="Worldwide", is_remote=True)
    else:
        kwargs["location"] = region["label"]
    if site in ("indeed", "glassdoor"):
        kwargs["country_indeed"] = region["indeed"]
    if site == "linkedin":
        kwargs["fetch_description"] = bool(scraping.get("linkedin_descriptions", True))
    if scraping.get("proxies"):
        kwargs["proxies"] = list(scraping["proxies"])
    return kwargs


def plan(site, ctx):
    searches = []
    for region in covered_regions(site, ctx.regions):
        for role, phrases in ctx.role_queries.items():
            query = or_query(phrases)
            if not query:
                continue
            kwargs = _kwargs(site, region, query, ctx)

            def fetch(kwargs=kwargs, region=region):
                return [normalise(row, region) for row in _scrape(**kwargs)]

            searches.append(Search(site, SITE_NAMES[site], f"{region['label']} · {role}", fetch, region,
                                   {"role": role, "region": region["id"]}))
    return searches
