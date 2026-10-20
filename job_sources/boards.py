"""Free, key-less job APIs: national job exchanges, remote boards and company career pages.

Boards that publish one small feed (Remotive, Remote OK, Jobicy, Arbeitnow) are
read once per run and narrowed by the relevance gate; boards with a search API
(Himalayas, Bundesagentur, JobTech) get one request per search phrase.
"""
import base64
import math
import re
from datetime import UTC, datetime

import requests

from job_sources import COMPANY_BOARD_ATS, USER_AGENT, Search, covered_regions, in_region, plain_text, to_iso

TIMEOUT = 30
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}
BA_API = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
BA_HEADERS = {**HEADERS, "X-API-Key": "jobboerse-jobsuche"}


def _get_json(url, params=None, headers=None):
    response = requests.get(url, params=params, headers=headers or HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def _list(payload, key):
    value = payload.get(key) if isinstance(payload, dict) else None
    return [item for item in value or [] if isinstance(item, dict)]


def remote_location(restriction):
    if isinstance(restriction, list):
        restriction = ", ".join(str(part) for part in restriction if part)
    restriction = str(restriction or "").strip()
    return f"Remote · {restriction}" if restriction else "Remote · Worldwide"


def with_level(description, level):
    if isinstance(level, list):
        level = ", ".join(str(part) for part in level if part)
    return f"{description}\n\nSeniority level: {level}".strip() if level else description


# --- Remote boards -----------------------------------------------------------------------

def fetch_remotive():
    payload = _get_json("https://remotive.com/api/remote-jobs")
    return [{
        "title": job.get("title", ""), "company_name": job.get("company_name", ""),
        "description": plain_text(job.get("description")),
        "location": remote_location(job.get("candidate_required_location")),
        "url": job.get("url", ""), "created": job.get("publication_date", ""),
        "contract_type": job.get("job_type", ""), "category": job.get("category", ""),
    } for job in _list(payload, "jobs")]


def fetch_himalayas(query):
    payload = _get_json("https://himalayas.app/jobs/api/search", params={"q": query})
    return [{
        "title": job.get("title", ""), "company_name": job.get("companyName", ""),
        "description": with_level(plain_text(job.get("description") or job.get("excerpt")), job.get("seniority")),
        "location": remote_location(job.get("locationRestrictions")),
        "url": job.get("applicationLink") or job.get("guid", ""), "created": to_iso(job.get("pubDate")),
        "contract_type": job.get("employmentType", ""),
    } for job in _list(payload, "jobs")]


def fetch_jobicy():
    payload = _get_json("https://jobicy.com/api/v2/remote-jobs", params={"count": 100})
    return [{
        "title": plain_text(job.get("jobTitle")), "company_name": job.get("companyName", ""),
        "description": with_level(plain_text(job.get("jobDescription") or job.get("jobExcerpt")),
                                  job.get("jobLevel")),
        "location": remote_location(job.get("jobGeo")), "url": job.get("url", ""),
        "created": job.get("pubDate", ""),
    } for job in _list(payload, "jobs")]


def fetch_remoteok():
    payload = _get_json("https://remoteok.com/api")
    jobs = [job for job in payload if isinstance(job, dict) and job.get("position")] if isinstance(payload, list) else []
    return [{
        "title": job.get("position", ""), "company_name": job.get("company", ""),
        "description": plain_text(job.get("description")),
        "location": remote_location(job.get("location")), "url": job.get("url", ""),
        "created": job.get("date", ""),
    } for job in jobs]


# --- Country boards ----------------------------------------------------------------------

def fetch_arbeitnow(pages=2):
    jobs = []
    for page in range(1, pages + 1):
        batch = _list(_get_json("https://www.arbeitnow.com/api/job-board-api", params={"page": page}), "data")
        jobs += batch
        if len(batch) < 100:
            break
    return [{
        "title": job.get("title", ""), "company_name": job.get("company_name", ""),
        "description": plain_text(job.get("description")),
        "location": remote_location(job.get("location")) if job.get("remote") else job.get("location", ""),
        "url": job.get("url", ""), "created": to_iso(job.get("created_at") or job.get("created")),
        "contract_type": ", ".join(job.get("job_types") or []),
    } for job in jobs]


def _ba_details(refnr):
    encoded = base64.b64encode(refnr.encode()).decode()
    try:
        detail = _get_json(f"{BA_API}/pc/v4/jobdetails/{encoded}", headers=BA_HEADERS)
    except (requests.RequestException, ValueError):
        return ""
    return plain_text(detail.get("stellenangebotsBeschreibung") or detail.get("stellenbeschreibung") or "")


def fetch_arbeitsagentur(query, ctx, region):
    params = {"was": query, "size": min(ctx.results_per_search, 100), "page": 1,
              "veroeffentlichtseit": max(1, min(100, math.ceil(ctx.window_hours / 24)))}
    payload = _get_json(f"{BA_API}/pc/v6/jobs", params=params, headers=BA_HEADERS)
    excluded = [word.lower() for word in ctx.settings.get("exclude_title_keywords", [])]
    items = []
    for job in _list(payload, "ergebnisliste") or _list(payload, "stellenangebote"):
        title = job.get("stellenangebotsTitel") or job.get("titel") or job.get("beruf") or ""
        refnr = job.get("referenznummer") or job.get("refnr") or ""
        places = job.get("stellenlokationen") or ([{"adresse": job["arbeitsort"]}] if job.get("arbeitsort") else [])
        town = ((places[0] or {}).get("adresse") or {}).get("ort", "") if places else ""
        # Detail pages carry the description; skip them for titles the gate rejects anyway.
        wanted = refnr and not any(re.search(rf"\b{re.escape(word)}\b", title.lower()) for word in excluded)
        items.append({
            "title": title, "company_name": job.get("firma") or job.get("arbeitgeber") or "",
            "description": _ba_details(refnr) if wanted else "",
            "location": in_region(town, region),
            "url": f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}" if refnr else "",
            "created": job.get("datumErsteVeroeffentlichung") or job.get("aktuelleVeroeffentlichungsdatum") or "",
        })
    return items


def fetch_jobtech(query, ctx, region):
    after = datetime.fromtimestamp(ctx.cutoff, UTC).strftime("%Y-%m-%dT%H:%M:%S")
    params = {"q": query, "limit": min(ctx.results_per_search, 100), "published-after": after}
    payload = _get_json("https://jobsearch.api.jobtechdev.se/search", params=params)
    items = []
    for job in _list(payload, "hits"):
        description = plain_text((job.get("description") or {}).get("text", ""))
        if job.get("experience_required") is False:
            description += "\n\nNo experience required (entry level)."
        address = job.get("workplace_address") or {}
        items.append({
            "title": job.get("headline", ""), "company_name": (job.get("employer") or {}).get("name", ""),
            "description": description,
            "location": in_region(address.get("municipality") or address.get("city") or "", region),
            "url": job.get("webpage_url", ""), "created": job.get("publication_date", ""),
        })
    return items


# --- Company career boards -----------------------------------------------------------------

def parse_company_board(entry):
    """'greenhouse:collibra' -> ('greenhouse', 'collibra'); None when malformed."""
    ats, _, slug = str(entry).strip().partition(":")
    ats, slug = ats.strip().lower(), slug.strip()
    if ats not in COMPANY_BOARD_ATS or not re.fullmatch(r"[A-Za-z0-9._-]+", slug):
        return None
    return ats, slug


def fetch_company_board(ats, slug):
    if ats == "greenhouse":
        payload = _get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", params={"content": "true"})
        return [{
            "title": job.get("title", ""), "company_name": job.get("company_name") or slug,
            "description": plain_text(job.get("content")), "location": (job.get("location") or {}).get("name", ""),
            "url": job.get("absolute_url", ""), "created": job.get("first_published") or job.get("updated_at", ""),
        } for job in _list(payload, "jobs")]
    if ats == "lever":
        payload = _get_json(f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"})
        jobs = [job for job in payload if isinstance(job, dict)] if isinstance(payload, list) else []
        return [{
            "title": job.get("text", ""), "company_name": slug,
            "description": "\n".join([job.get("descriptionPlain", "")] + [
                plain_text(f"{part.get('text', '')}\n{part.get('content', '')}") for part in job.get("lists") or []]),
            "location": ", ".join(filter(None, [(job.get("categories") or {}).get("location", ""),
                                                "Remote" if job.get("workplaceType") == "remote" else ""])),
            "url": job.get("hostedUrl", ""), "created": to_iso(job.get("createdAt")),
            "contract_type": (job.get("categories") or {}).get("commitment", ""),
        } for job in jobs]
    if ats == "ashby":
        payload = _get_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
        return [{
            "title": job.get("title", "").strip(), "company_name": slug,
            "description": job.get("descriptionPlain") or plain_text(job.get("descriptionHtml")),
            "location": "; ".join(filter(None, [job.get("location", "")] + [
                part.get("location", "") for part in job.get("secondaryLocations") or []])),
            "url": job.get("jobUrl", ""), "created": job.get("publishedAt", ""),
            "contract_type": job.get("employmentType", ""),
        } for job in _list(payload, "jobs")]
    if ats == "recruitee":
        payload = _get_json(f"https://{slug}.recruitee.com/api/offers/")
        return [{
            "title": job.get("title", ""), "company_name": job.get("company_name") or slug,
            "description": with_level(plain_text(job.get("description")), job.get("experience_code")),
            "location": job.get("location") or ", ".join(filter(None, [job.get("city"), job.get("country")])),
            "url": job.get("careers_url", ""), "created": to_iso(job.get("published_at")),
        } for job in _list(payload, "offers")]
    if ats == "smartrecruiters":
        payload = _get_json(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings", params={"limit": 100})
        return [{
            "title": job.get("name", ""), "company_name": (job.get("company") or {}).get("name") or slug,
            "description": with_level("", (job.get("experienceLevel") or {}).get("label")),
            "location": (job.get("location") or {}).get("fullLocation", ""),
            "url": f"https://jobs.smartrecruiters.com/{slug}/{job.get('id', '')}",
            "created": job.get("releasedDate", ""),
        } for job in _list(payload, "content")]
    raise ValueError(f"Unsupported career board: {ats}")


# --- Planning ------------------------------------------------------------------------------

def plan(source, ctx):
    """Searches for one board source. Region-less feeds run once if any covered region is selected."""
    regions_covered = covered_regions(source, ctx.regions)
    if source != "company_boards" and not regions_covered:
        return []
    if source == "remotive":
        return [Search(source, "Remotive", "All remote jobs", fetch_remotive)]
    if source == "jobicy":
        return [Search(source, "Jobicy", "Latest remote jobs", fetch_jobicy)]
    if source == "remoteok":
        return [Search(source, "Remote OK", "Latest remote jobs", fetch_remoteok)]
    if source == "arbeitnow":
        return [Search(source, "Arbeitnow", "Latest jobs", fetch_arbeitnow)]
    if source == "himalayas":
        return [Search(source, "Himalayas", query, lambda query=query: fetch_himalayas(query))
                for query in ctx.queries()]
    if source in ("arbeitsagentur", "jobtech"):
        fetch = fetch_arbeitsagentur if source == "arbeitsagentur" else fetch_jobtech
        name = "Bundesagentur für Arbeit" if source == "arbeitsagentur" else "Arbetsförmedlingen"
        region = regions_covered[0]
        return [Search(source, name, f"{region['label']} · {query}",
                       lambda query=query: fetch(query, ctx, region), region)
                for query in ctx.queries()]
    if source == "company_boards":
        boards = [parsed for parsed in map(parse_company_board, ctx.settings.get("company_boards", [])) if parsed]
        return [Search(source, ats.title() if ats != "smartrecruiters" else "SmartRecruiters", f"{slug} ({ats})",
                       lambda ats=ats, slug=slug: fetch_company_board(ats, slug))
                for ats, slug in boards]
    raise ValueError(f"Unknown board source: {source}")

