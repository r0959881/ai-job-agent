"""Job search for the web app: the catalog for the Start-run wizard, the plan of a run and one search at a time.

The browser drives a run: it asks for the plan, then runs the searches one by
one and keeps the jobs it gets back on the user's own device. Each request does
one bounded piece of work, so it ends well inside a shared host's request
timeout, and nothing about the jobs is stored on the server.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

import agent_settings
import discovery
import job_sources
import languages
import regions
from api import server_config
from api.routers.settings import _role_profiles
from discovery import adzuna_searches, normalise_job, run_scope
from job_sources import websearch

router = APIRouter(prefix="/api/search", tags=["search"])

# Sources the hosted app offers (Gmail alerts need Google's restricted-scope review).
HOSTED_SOURCES = [key for key in job_sources.SOURCE_KEYS if key != "gmail"]
# LinkedIn reads one detail page per result, so a search is capped to stay inside the request timeout.
HOSTED_MAX_RESULTS = 20


class RunScope(BaseModel):
    sources: list[str] | None = None
    regions: list[str] | None = None
    roles: list[str] | None = None
    # Empty list: any language. Missing: the user's default languages.
    languages: list[str] | None = None
    time_window_hours: int | None = Field(None, ge=1, le=24 * 60)

    @field_validator("sources")
    @classmethod
    def known_sources(cls, value):
        if value is None:
            return value
        unknown = set(value) - set(HOSTED_SOURCES)
        if unknown:
            raise ValueError(f"Unknown source(s): {', '.join(sorted(unknown))}")
        if not value:
            raise ValueError("Pick at least one source")
        return value

    @field_validator("regions")
    @classmethod
    def known_regions(cls, value):
        if value is None:
            return value
        ids = list(dict.fromkeys(str(region).strip().upper() for region in value))
        unknown = [region for region in ids if not regions.get(region)]
        if unknown:
            raise ValueError(f"Unknown region(s): {', '.join(unknown)}")
        if not ids:
            raise ValueError("Pick at least one region")
        return ids

    @field_validator("languages")
    @classmethod
    def known_languages(cls, value):
        if value is None:
            return value
        ids = list(dict.fromkeys(str(code).strip().lower() for code in value))
        unknown = [code for code in ids if not languages.get(code)]
        if unknown:
            raise ValueError(f"Unknown language(s): {', '.join(unknown)}")
        return ids

    @field_validator("roles")
    @classmethod
    def some_roles(cls, value):
        if value is None:
            return value
        names = list(dict.fromkeys(str(role).strip() for role in value if str(role).strip()))
        if not names:
            raise ValueError("Pick at least one role")
        return names


class SearchRun(RunScope):
    index: int = Field(ge=0)
    source: str = ""
    label: str = ""


def _context(body: RunScope):
    settings = agent_settings.load()
    window = int(body.time_window_hours or settings["time_window_hours"])
    settings, ctx = run_scope(settings, body.regions, body.roles, window)
    scraping = settings.setdefault("scraping", {})
    scraping["time_budget"] = server_config.search_time_budget()
    scraping["results_per_search"] = min(int(scraping.get("results_per_search", 25)), HOSTED_MAX_RESULTS)
    return settings, ctx


def _chosen(body: RunScope, settings):
    if body.sources is not None:
        return [key for key in HOSTED_SOURCES if key in body.sources]
    return [key for key in HOSTED_SOURCES if settings["sources"].get(key)]


def _searches(body: RunScope, settings, ctx):
    """Every search of the run, in a stable order (the browser addresses them by index)."""
    chosen = _chosen(body, settings)
    searches = []
    for key in job_sources.SCRAPERS + job_sources.BOARDS:
        if key in chosen:
            searches += job_sources.plan(key, ctx)
    if "adzuna" in chosen and discovery.adzuna_credentials():
        searches += adzuna_searches(ctx)
    return searches


def _skip_reason(key, settings):
    if key == "adzuna" and not discovery.adzuna_credentials():
        return "add your Adzuna keys in Settings → Integrations"
    if key == "company_boards" and not settings.get("company_boards"):
        return "no companies followed yet (Settings → Search)"
    if key == "websearch" and not websearch.configured():
        return "add a Brave Search or Groq key in Settings → Integrations"
    return "not available in the selected regions"


def _languages(body: RunScope, settings):
    return body.languages if body.languages is not None else settings.get("languages") or []


@router.post("/plan")
def plan(body: RunScope):
    settings, ctx = _context(body)
    searches = _searches(body, settings, ctx)
    planned = {search.source for search in searches}
    skipped = [{"source": key, "label": job_sources.SOURCES[key]["label"], "kind": job_sources.SOURCES[key]["kind"],
                "reason": _skip_reason(key, settings)}
               for key in _chosen(body, settings) if key not in planned]
    return {
        "searches": [{"index": index, "source": search.source, "name": search.name, "label": search.label,
                      "kind": job_sources.SOURCES[search.source]["kind"]} for index, search in enumerate(searches)],
        "skipped": skipped,
        "window_hours": ctx.window_hours,
        "languages": _languages(body, settings),
        "regions": [region["label"] for region in ctx.regions],
    }


def _excluded(row, reason):
    return {key: row.get(key, "") for key in ("id", "title", "company", "location", "posted_at", "source")} | {
        "exclusion_reason": reason}


@router.post("/run")
def run_one(body: SearchRun):
    """Run one search of the plan and return the jobs that pass every filter."""
    settings, ctx = _context(body)
    searches = _searches(body, settings, ctx)
    search = searches[body.index] if body.index < len(searches) else None
    if search is None or (body.source and search.source != body.source) or (body.label and search.label != body.label):
        raise HTTPException(409, "The search plan changed (were the settings edited during the run?). "
                                 "Start the run again.")
    counts = {"discovered": 0, "kept": 0, "filtered": 0, "language_filtered": 0}
    try:
        items = search.fetch()
    except job_sources.SourceUnavailable as error:  # a spent quota: the browser warns once and skips the source
        return {"ok": False, "unavailable": True, "error": str(error)[:300], "jobs": [], "excluded": [],
                "counts": counts}
    except Exception as error:  # one broken source must not stop the run; the browser counts the failure
        return {"ok": False, "error": f"{type(error).__name__}: {str(error)[:200]}", "jobs": [], "excluded": [],
                "counts": counts}
    counts["discovered"] = len(items)
    picked_languages = _languages(body, settings)
    jobs, excluded = [], []
    for item in items:
        if not job_sources.is_fresh(item, ctx.cutoff):
            counts["filtered"] += 1
            continue
        row = normalise_job(item, search.name, settings)
        if row is None or (body.roles and row["role_family"] not in body.roles):
            counts["filtered"] += 1
            continue
        keep, reason = languages.check_job(row["title"], row["description"], picked_languages)
        if not keep:
            counts["language_filtered"] += 1
            excluded.append(_excluded(row, reason))
            continue
        jobs.append(row)
    counts["kept"] = len(jobs)
    return {"ok": True, "jobs": jobs, "excluded": excluded, "counts": counts}


# ------------------------------------------------------------------------------ catalog

def _roles(settings):
    """Resume role profiles first, then target roles that have no profile yet."""
    profiles = _role_profiles() or {}
    names = list(dict.fromkeys([*profiles, *settings["target_roles"]]))
    return [
        {
            "name": name,
            "focus": getattr(profiles.get(name), "focus", "") or "",
            "has_profile": name in profiles,
            "keywords": settings["target_roles"].get(name, []),
            "queries": settings["search_queries"].get(name) or [name],
            "searches_by_name": not settings["search_queries"].get(name),
        }
        for name in names
    ]


def _configured(key, settings):
    if key == "adzuna":
        return discovery.adzuna_credentials() is not None, "Add your Adzuna keys in Settings → Integrations."
    if key == "company_boards":
        return bool(settings["company_boards"]), "Follow companies in Settings → Search first."
    if key == "websearch":
        return websearch.configured(), "Add a Brave Search (or Groq) key in Settings → Integrations."
    return True, ""


def _sources(settings):
    all_regions = list(regions.REGIONS.values())
    items = []
    for key in HOSTED_SOURCES:
        source = job_sources.SOURCES[key]
        configured, hint = _configured(key, settings)
        items.append({
            "key": key,
            "label": source["label"],
            "kind": source["kind"],
            "description": source["description"],
            "default": bool(settings["sources"].get(key, source["default"])),
            "configured": configured,
            "setup_hint": hint,
            "regions": [region["id"] for region in all_regions if job_sources.covers(key, region)],
        })
    return items


@router.get("/catalog")
def catalog():
    settings = agent_settings.load()
    return {
        "regions": regions.public_catalog(),
        "groups": regions.GROUPS,
        "languages": languages.public_catalog(),
        "roles": _roles(settings),
        "sources": _sources(settings),
        "defaults": {
            "regions": settings["regions"],
            "roles": list(settings["target_roles"]),
            "languages": settings["languages"],
            "time_window_hours": settings["time_window_hours"],
        },
    }
