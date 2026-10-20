import hashlib
import os
import re
import sqlite3
import json
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

import agent_settings
import job_sources
import regions
import user_scope
from agent_log import check_cancelled, log, step
from config import ENV_PATH
from database import init_db, transaction

load_dotenv(ENV_PATH)

# Built-in defaults. The effective values are read from agent_settings.yaml at
# call time, so edits in the web UI apply without a restart.
TARGET_ROLES = agent_settings.DEFAULTS["target_roles"]

TARGET_KEYWORDS = [
    keyword
    for role_keywords in TARGET_ROLES.values()
    for keyword in role_keywords
]
TARGET_KEYWORDS += agent_settings.DEFAULTS["extra_keywords"]

SEARCH_QUERIES = agent_settings.DEFAULTS["search_queries"]

ENTRY_LEVEL_KEYWORDS = agent_settings.DEFAULTS["entry_level_keywords"]

EXPERIENCE_PATTERN = re.compile(
    r"\b(?:0\s*(?:-|to)\s*2|1\s*(?:-|to)\s*2|[012])\s*years?\b"
    r"|\b(?:one|two)\s+years?\b"
)

# Reject Seniority Level Keywords
EXCLUDE_TITLE_KEYWORDS = agent_settings.DEFAULTS["exclude_title_keywords"]

# Accepted job locations
ALLOWED_LOCATIONS = agent_settings.DEFAULTS["allowed_locations"]
NON_BELGIAN_LOCATIONS = agent_settings.DEFAULTS["blocked_locations"]


def get_target_roles(settings=None):
    return (settings or agent_settings.load())["target_roles"]


def classify_target_role(title, description="", settings=None):
    """Return the closest requested role family for a job listing."""
    text = clean_text(f"{title} {description}")
    role_scores = {
        role: sum(keyword in text for keyword in keywords)
        for role, keywords in get_target_roles(settings).items()
    }
    if not role_scores:
        return None
    best_role, best_score = max(role_scores.items(), key=lambda item: item[1])
    return best_role if best_score else None


def generate_job_id(company, title):
    raw_str = f"{company.lower().strip()}_{title.lower().strip()}"
    return hashlib.md5(raw_str.encode("utf-8")).hexdigest()

def clean_text(raw_html):
    cleanr = re.compile("<.*?>")
    cleantext = re.sub(cleanr, " ", raw_html)
    return " ".join(cleantext.lower().split())


def contains_location_marker(text, markers):
    return any(re.search(rf"\b{re.escape(marker)}\b", text) for marker in markers)

def is_relevant_job(title, description, location="", allow_non_entry=False, settings=None):
    settings = settings or agent_settings.load()
    title_clean = clean_text(title)
    desc_clean = clean_text(description)
    loc_clean = clean_text(location)

    # Prefer the source location so a London location in a description cannot
    # make an unrelated job look eligible.
    combined_text = f"{title_clean} {desc_clean} {loc_clean}"
    location_text = loc_clean or combined_text
    if contains_location_marker(location_text, settings["blocked_locations"]):
        return False
    if not contains_location_marker(location_text, settings["allowed_locations"]):
        return False

    # 2. SENIORITY CHECK: Reject Senior, Director, Lead, VP roles
    if any(ex in title_clean for ex in settings["exclude_title_keywords"]):
        return False

    # 3. SCOPE CHECK: Ensure the job title/desc matches Data/BI roles
    target_keywords = agent_settings.all_target_keywords(settings)
    has_tech_match = any(keyword in combined_text for keyword in target_keywords)
    has_entry_signal = any(keyword in combined_text for keyword in settings["entry_level_keywords"])
    has_allowed_experience = bool(EXPERIENCE_PATTERN.search(combined_text))

    return has_tech_match and (
        allow_non_entry or has_entry_signal or has_allowed_experience
    )

def normalise_job(item, source_type, settings, discovered_at=None):
    """A source item as a job row, or None when the relevance gate rejects it."""
    title = item.get("title", "") or ""
    company = item.get("company_name", "") or item.get("company", "") or "Unknown"
    if isinstance(company, dict):
        company = company.get("display_name", "Unknown")
    description = item.get("description", "") or ""
    location = item.get("location", "") or ""

    trusted_alert_source = source_type in set(settings["trusted_alert_sources"])
    if not title or not is_relevant_job(title, description, location, allow_non_entry=trusted_alert_source,
                                        settings=settings):
        return None
    company_data = item.get("company", {})
    if isinstance(company_data, dict):
        company = item.get("company_name", "") or company_data.get("display_name", "Unknown")
    return {
        "id": generate_job_id(company, title), "title": title, "company": company, "location": location,
        "url": item.get("url", "") or item.get("redirect_url", "") or "", "source": source_type,
        "description": description,
        "category": item.get("category", "") or item.get("category_name", "") or "",
        "contract_type": item.get("contract_type", "") or item.get("contract", "") or "",
        "salary_min": item.get("salary_min"), "salary_max": item.get("salary_max"),
        "salary_currency": item.get("salary_currency", "") or "",
        "posted_at": job_sources.to_iso(item.get("created") or item.get("date")),
        "discovered_at": discovered_at or datetime.now(timezone.utc).isoformat(),
        # The title decides; the description only breaks the tie when the title names no role.
        "role_family": (classify_target_role(title, settings=settings)
                        or classify_target_role(title, description, settings=settings) or ""),
    }


def save_jobs_to_db(jobs, source_type, settings=None):
    new_jobs_count = 0
    duplicate_count = 0
    filtered_count = 0
    discovered_at = datetime.now(timezone.utc).isoformat()
    settings = settings or agent_settings.load()

    # Both API discovery and Gmail ingestion use this same storage boundary.
    init_db()
    with transaction() as conn:
        for item in jobs:
            row = normalise_job(item, source_type, settings, discovered_at)
            if row is None:
                filtered_count += 1
                continue
            job_id, title, company, location, job_url = (row["id"], row["title"], row["company"], row["location"],
                                                         row["url"])
            description, category, contract_type = row["description"], row["category"], row["contract_type"]
            salary_min, salary_max, salary_currency = row["salary_min"], row["salary_max"], row["salary_currency"]
            posted_at, role_family = row["posted_at"], row["role_family"]

            source_data = json.dumps(item, default=str)
            existing_job = conn.execute(
                "SELECT 1 FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            try:
                conn.execute(
                    """INSERT INTO jobs
                    (id, title, company, location, url, source, description,
                     category, contract_type, salary_min, salary_max,
                     salary_currency, posted_at, discovered_at, source_data, role_family)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        source = CASE
                            WHEN instr('|' || jobs.source || '|', '|' || excluded.source || '|') > 0
                                THEN jobs.source
                            ELSE jobs.source || ' | ' || excluded.source
                        END,
                        description = CASE WHEN jobs.description = '' THEN excluded.description ELSE jobs.description END,
                        location = CASE WHEN jobs.location = '' THEN excluded.location ELSE jobs.location END,
                        url = CASE WHEN jobs.url = '' THEN excluded.url ELSE jobs.url END,
                        source_data = CASE WHEN jobs.source_data = '' THEN excluded.source_data ELSE jobs.source_data END,
                        role_family = CASE WHEN COALESCE(jobs.role_family, '') = '' THEN excluded.role_family ELSE jobs.role_family END""",
                    (job_id, title, company, location, job_url, source_type,
                     description, category, contract_type, salary_min, salary_max,
                     salary_currency, posted_at, discovered_at, source_data, role_family),
                )
                if existing_job:
                    duplicate_count += 1
                else:
                    new_jobs_count += 1
            except sqlite3.IntegrityError:
                duplicate_count += 1
                continue

    log(f"🎯 [{source_type}] Saved {new_jobs_count} job(s) | ({duplicate_count} duplicates, {filtered_count} filtered)")
    return {
        "discovered": len(jobs),
        "new": new_jobs_count,
        "duplicates": duplicate_count,
        "filtered": filtered_count,
    }


def _empty_counts():
    return {"discovered": 0, "new": 0, "duplicates": 0, "filtered": 0}


def add_counts(total, counts):
    for key in total:
        total[key] += (counts or {}).get(key, 0)
    return total


def run_scope(settings, region_ids=None, roles=None, window_hours=None):
    """Settings and search context for one run.

    Regions picked for the run replace the allowed locations, so only jobs in
    those places are kept. Without a pick, the default regions from the settings
    are added to the allowed locations. Picked roles narrow the role families;
    a role with no keywords or search phrases is searched by its own name.
    """
    settings = dict(settings)
    explicit_regions = region_ids is not None
    region_ids = list(region_ids) if explicit_regions else list(settings.get("regions") or [])
    if roles is not None:
        settings["target_roles"] = {
            name: settings["target_roles"].get(name) or [name.lower()] for name in roles
        }
    role_queries = {
        name: settings["search_queries"].get(name) or [name] for name in settings["target_roles"]
    }
    if explicit_regions:
        allowed = regions.markers(region_ids)
    else:
        allowed = list(dict.fromkeys(settings["allowed_locations"] + regions.markers(region_ids)))
    settings["allowed_locations"] = allowed
    settings["blocked_locations"] = [place for place in settings["blocked_locations"] if place not in allowed]
    context = job_sources.Context(
        regions=regions.resolve(region_ids), role_queries=role_queries,
        window_hours=int(window_hours or settings["time_window_hours"]), settings=settings,
    )
    return settings, context


def adzuna_credentials():
    app_id = user_scope.secret("ADZUNA_APP_ID")
    app_key = user_scope.secret("ADZUNA_APP_KEY")
    if not app_id or not app_key or "your_app" in app_id:
        return None
    return app_id, app_key


def fetch_adzuna(keyword, region, page=1, settings=None):
    """One Adzuna search inside a region's country."""
    app_id, app_key = adzuna_credentials()
    adzuna = (settings or agent_settings.load())["adzuna"]
    url = f"https://api.adzuna.com/v1/api/jobs/{region['adzuna']}/search/{page}"
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": adzuna["results_per_page"],
        "what": keyword,
    }
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    results = response.json().get("results", [])
    if not results:
        log(f"ℹ️ Adzuna returned no listings for '{keyword}' in {region['label']}.")
    return [
        {
            "title": result.get("title", ""),
            "company_name": result.get("company", {}).get("display_name", "Unknown"),
            "description": result.get("description", ""),
            "location": job_sources.in_region(result.get("location", {}).get("display_name", ""), region),
            "url": result.get("redirect_url", ""),
            "created": result.get("created", ""),
            "salary_min": result.get("salary_min"),
            "salary_max": result.get("salary_max"),
            "contract_type": result.get("contract_type", "") or "",
            "category": (result.get("category") or {}).get("label", ""),
        }
        for result in results
    ]


def adzuna_searches(ctx):
    return [
        job_sources.Search("adzuna", f"Adzuna {region['label']}", f"{region['label']} · {keyword}",
                           lambda keyword=keyword, region=region: fetch_adzuna(keyword, region, settings=ctx.settings),
                           region)
        for region in job_sources.covered_regions("adzuna", ctx.regions)
        for keyword in ctx.queries()
    ]


# A source that fails this many searches in a row is probably blocking us; skip the rest.
MAX_CONSECUTIVE_FAILURES = 2


def run_searches(step_name, searches, settings, ctx):
    """Run searches one by one with progress events; returns the summed counts."""
    totals = _empty_counts()
    per_source = {}
    failures = {}
    errors = 0
    gave_up = set()
    for index, search in enumerate(searches, start=1):
        check_cancelled()
        counts = per_source.setdefault(search.name, _empty_counts())
        if search.source in gave_up:
            errors += 1
        else:
            log(f"🔍 {search.name}: {search.label}")
            try:
                items = search.fetch()
            except Exception as error:  # one broken source must not stop the run
                errors += 1
                failures[search.source] = failures.get(search.source, 0) + 1
                log(f"❌ {search.name} ({search.label}): {type(error).__name__}: {str(error)[:200]}", level="error")
                if failures[search.source] >= MAX_CONSECUTIVE_FAILURES:
                    gave_up.add(search.source)
                    log(f"⚠️ {search.name} failed {MAX_CONSECUTIVE_FAILURES} times in a row; "
                        "skipping its remaining searches in this run.", level="warning")
            else:
                failures[search.source] = 0
                fresh = [item for item in items if job_sources.is_fresh(item, ctx.cutoff)]
                saved = save_jobs_to_db(fresh, search.name, settings)
                saved["discovered"] += len(items) - len(fresh)
                saved["filtered"] += len(items) - len(fresh)
                add_counts(counts, saved)
                add_counts(totals, saved)
        step(step_name, "progress", f"{search.name} · {search.label} ({index} of {len(searches)})",
             {"done": index, "total": len(searches), **totals, "per_source": per_source})
    summary = " · ".join(f"{name} {counts['new']} new" for name, counts in per_source.items())
    message = f"{totals['new']} new, {totals['duplicates']} already known, {totals['filtered']} filtered"
    if summary:
        message += f" ({summary})"
    if errors:
        message += f". {errors} of {len(searches)} searches failed or were skipped"
    step(step_name, "warning" if errors else "succeeded", message,
         {**totals, "per_source": per_source, "errors": errors})
    return totals


STEP_SOURCES = {
    "scrape": ("Web scraping", job_sources.SCRAPERS),
    "boards": ("Job boards", job_sources.BOARDS),
}


def _run_group(step_name, sources, settings, ctx):
    title, members = STEP_SOURCES[step_name]
    chosen = [key for key in members if key in sources]
    if not chosen:
        step(step_name, "skipped", f"{title}: no sources selected for this run.")
        return _empty_counts()
    searches = [search for key in chosen for search in job_sources.plan(key, ctx)]
    if not searches:
        reasons = [
            f"{job_sources.SOURCES[key]['label']}: no companies followed yet (Settings → Search)"
            if key == "company_boards" else f"{job_sources.SOURCES[key]['label']}: not available in the selected regions"
            for key in chosen
        ]
        step(step_name, "skipped", f"{title} skipped. " + "; ".join(reasons) + ".")
        return _empty_counts()
    labels = ", ".join(dict.fromkeys(search.name for search in searches))
    step(step_name, "started", f"{len(searches)} searches on {labels}", {"done": 0, "total": len(searches)})
    return run_searches(step_name, searches, settings, ctx)


def run_adzuna(settings, ctx):
    if not adzuna_credentials():
        log("⚠️ Adzuna credentials missing in .env (skipping Adzuna)", level="warning")
        step("adzuna", "skipped", "Adzuna credentials are missing in .env, so Adzuna was skipped.")
        return _empty_counts()
    searches = adzuna_searches(ctx)
    if not searches:
        step("adzuna", "skipped", "Adzuna does not cover the selected regions.")
        return _empty_counts()
    step("adzuna", "started", "Searching Adzuna", {"done": 0, "total": len(searches)})
    return run_searches("adzuna", searches, settings, ctx)


DISCOVERY_SOURCES = set(job_sources.SOURCE_KEYS) - {"gmail"}


def run_discovery(sources=None, settings=None, ctx=None):
    """Search every non-email source. `sources` limits which run (default: all enabled in settings)."""
    init_db()
    if settings is None or ctx is None:
        settings, ctx = run_scope(agent_settings.load())
    enabled = {name for name, on in settings["sources"].items() if on}
    sources = set(sources) if sources is not None else enabled
    region_names = ", ".join(region["label"] for region in ctx.regions) or "no regions"
    log(f"🌍 Searching for jobs in {region_names} for {len(ctx.role_queries)} role(s)...\n")
    totals = _empty_counts()

    add_counts(totals, _run_group("scrape", sources, settings, ctx))
    check_cancelled()
    add_counts(totals, _run_group("boards", sources, settings, ctx))
    check_cancelled()
    if "adzuna" in sources:
        add_counts(totals, run_adzuna(settings, ctx))
    else:
        step("adzuna", "skipped", "Adzuna is turned off for this run.")
    return totals


if __name__ == "__main__":
    run_discovery()
