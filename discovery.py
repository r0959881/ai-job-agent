import hashlib
import os
import re
import sqlite3
import json
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

import agent_settings
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


def get_target_roles():
    return agent_settings.get("target_roles")


def classify_target_role(title, description=""):
    """Return the closest requested role family for a job listing."""
    text = clean_text(f"{title} {description}")
    role_scores = {
        role: sum(keyword in text for keyword in keywords)
        for role, keywords in get_target_roles().items()
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

def save_jobs_to_db(jobs, source_type):
    new_jobs_count = 0
    duplicate_count = 0
    filtered_count = 0
    discovered_at = datetime.now(timezone.utc).isoformat()
    settings = agent_settings.load()

    # Both API discovery and Gmail ingestion use this same storage boundary.
    init_db()
    with transaction() as conn:
        for item in jobs:
            title = item.get("title", "") or ""
            company = item.get("company_name", "") or item.get("company", "") or "Unknown"
            if isinstance(company, dict):
                company = company.get("display_name", "Unknown")
            description = item.get("description", "") or ""
            location = item.get("location", "") or ""

            trusted_alert_source = source_type in set(settings["trusted_alert_sources"])
            if not title or not is_relevant_job(
                title,
                description,
                location,
                allow_non_entry=trusted_alert_source,
                settings=settings,
            ):
                filtered_count += 1
                continue

            job_id = generate_job_id(company, title)
            job_url = item.get("url", "") or item.get("redirect_url", "") or ""
            company_data = item.get("company", {})
            if isinstance(company_data, dict):
                company = item.get("company_name", "") or company_data.get("display_name", "Unknown")
            category = item.get("category", "") or item.get("category_name", "") or ""
            contract_type = item.get("contract_type", "") or item.get("contract", "") or ""
            salary_min = item.get("salary_min")
            salary_max = item.get("salary_max")
            salary_currency = item.get("salary_currency", "") or ""
            posted_at = item.get("created", "") or item.get("date", "") or ""
            role_family = classify_target_role(title) or ""

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


def fetch_arbeitnow_jobs(keyword="data"):
    """Fetch Arbeitnow listings and apply the same Belgian eligibility gate."""
    url = "https://www.arbeitnow.com/api/job-board-api"
    log(f"🔍 Searching Arbeitnow for '{keyword}' jobs...")
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        jobs = response.json().get("data", [])
        return save_jobs_to_db(jobs, "Arbeitnow")
    except (requests.RequestException, ValueError) as error:
        log(f"❌ Arbeitnow error: {error}", level="error")
        return None


def adzuna_credentials():
    app_id = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_APP_KEY")
    if not app_id or not app_key or "your_app" in app_id:
        return None
    return app_id, app_key


def fetch_adzuna_belgium(keyword="data engineer", location="belgium", page=1):
    """Fetches jobs specifically from Adzuna Belgium API."""
    credentials = adzuna_credentials()
    if not credentials:
        log("⚠️ Adzuna credentials missing in .env (skipping Adzuna)", level="warning")
        return None
    app_id, app_key = credentials
    adzuna = agent_settings.get("adzuna")

    url = f"https://api.adzuna.com/v1/api/jobs/{adzuna['country']}/search/{page}"
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": adzuna["results_per_page"],
        "what": keyword,
        "where": location
    }
    log(f"🔍 Searching Adzuna (BE) for '{keyword}' near '{location}'...")
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results", [])
        if not results:
            log(f"ℹ️ Adzuna returned no listings for '{keyword}' in Belgium.")
        formatted_jobs = [
            {
                "title": result.get("title", ""),
                "company_name": result.get("company", {}).get("display_name", "Unknown"),
                "description": result.get("description", ""),
                "location": result.get("location", {}).get("display_name", "Belgium"),
                "url": result.get("redirect_url", ""),
            }
            for result in results
        ]
        return save_jobs_to_db(formatted_jobs, "Adzuna Belgium")
    except (requests.RequestException, ValueError) as error:
        log(f"❌ Adzuna BE error: {error}", level="error")
        return None


def run_adzuna():
    settings = agent_settings.load()
    totals = _empty_counts()
    if not adzuna_credentials():
        step("adzuna", "skipped", "Adzuna credentials are missing in .env, so Adzuna was skipped.")
        for queries in settings["search_queries"].values():
            for _keyword in queries:
                fetch_adzuna_belgium()  # Prints the same warning per query as before.
        return totals
    step("adzuna", "started", "Searching Adzuna")
    errors = 0
    queries = [kw for queries in settings["search_queries"].values() for kw in queries]
    for index, keyword in enumerate(queries, start=1):
        check_cancelled()
        counts = fetch_adzuna_belgium(keyword=keyword, location=settings["adzuna"]["location"])
        errors += counts is None
        add_counts(totals, counts)
        step("adzuna", "progress", f"Query {index} of {len(queries)}", {"done": index, "total": len(queries), **totals})
    status = "warning" if errors else "succeeded"
    step("adzuna", status, f"{totals['new']} new, {totals['duplicates']} already known, {totals['filtered']} filtered"
         + (f", {errors} queries failed" if errors else ""), totals)
    return totals


def run_arbeitnow():
    step("arbeitnow", "started", "Fetching Arbeitnow")
    counts = fetch_arbeitnow_jobs()
    if counts is None:
        step("arbeitnow", "warning", "Arbeitnow could not be reached.", _empty_counts())
        return _empty_counts()
    step("arbeitnow", "succeeded", f"{counts['new']} new, {counts['filtered']} filtered", counts)
    return counts


def run_discovery(sources=None):
    """Search the API sources. `sources` limits which run (default: all enabled in settings)."""
    init_db()
    log("🇧🇪 Executing Targeted Belgian Job Discovery...\n")
    enabled = agent_settings.get("sources")
    sources = set(sources) if sources is not None else {name for name, on in enabled.items() if on}
    totals = _empty_counts()

    # Search every requested role family; the relevance gate below keeps only
    # Belgian, early-career listings that match the profile.
    if "adzuna" in sources:
        add_counts(totals, run_adzuna())
    else:
        step("adzuna", "skipped", "Adzuna is turned off for this run.")
    check_cancelled()
    if "arbeitnow" in sources:
        add_counts(totals, run_arbeitnow())
    else:
        step("arbeitnow", "skipped", "Arbeitnow is turned off for this run.")
    return totals

if __name__ == "__main__":
    run_discovery()
