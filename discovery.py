import hashlib
import os
import re
import sqlite3
import json
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv
from database import init_db

load_dotenv()

# Target roles for job discovery and CV tailoring.
TARGET_ROLES = {
    "Data Integration": [
        "data integration", "integration engineer", "etl developer",
        "etl engineer", "data ingestion", "integration specialist",
    ],
    "Data Science": [
        "data science", "data scientist", "machine learning",
        "machine learning engineer", "predictive analytics",
    ],
    "Data Engineer": [
        "data engineer", "analytics engineer", "data platform",
        "data pipeline", "data pipelines", "data architect",
    ],
    "Data Analyst": [
        "data analyst", "bi analyst", "business intelligence",
        "reporting analyst", "analytics specialist",
    ],
    "Functional Analyst (IT)": [
        "functional analyst", "it functional analyst", "business systems analyst",
        "requirements analyst", "functional consultant",
    ],
}

TARGET_KEYWORDS = [
    keyword
    for role_keywords in TARGET_ROLES.values()
    for keyword in role_keywords
]
TARGET_KEYWORDS += [
    "databricks", "pyspark", "fabric", "power bi", "sql", "python",
    "data modelling", "data modeling", "etl", "elt",
]

def classify_target_role(title, description=""):
    """Return the closest requested role family for a job listing."""
    text = clean_text(f"{title} {description}")
    role_scores = {
        role: sum(keyword in text for keyword in keywords)
        for role, keywords in TARGET_ROLES.items()
    }
    best_role, best_score = max(role_scores.items(), key=lambda item: item[1])
    return best_role if best_score else None

ENTRY_LEVEL_KEYWORDS = [
    "junior", "trainee", "traineeship", "intern", "internship", "graduate",
    "starter", "entry level", "entry-level", "early career",
]

EXPERIENCE_PATTERN = re.compile(
    r"\b(?:0\s*(?:-|to)\s*2|1\s*(?:-|to)\s*2|[012])\s*years?\b"
    r"|\b(?:one|two)\s+years?\b"
)

# Reject Seniority Level Keywords
EXCLUDE_TITLE_KEYWORDS = [
    "director", "senior manager", "head of", "lead", "vp", "chief",
    "principal", "senior", "manager", "paid search", "marketing manager",
    "sales executive", "recruiter", "hr manager", "account manager"
]

# Accepted job locations
ALLOWED_LOCATIONS = [
    "belgium", "belgië", "belgique", "mechelen", "antwerp", "antwerpen",
    "brussels", "bruxelles", "ghent", "gent", "leuven", "flanders", "vlaanderen",
    "netherlands", "nederland", "amsterdam", "rotterdam", "utrecht", "eindhoven",
]
NON_BELGIAN_LOCATIONS = [
    "germany", "deutschland", "düsseldorf", "dusseldorf", "berlin", "munich",
    "münchen", "frankfurt", "hamburg", "cologne", "köln", "stuttgart",
    "france", "paris", "uk", "united kingdom", "england", "scotland", "wales",
    "london", "manchester", "birmingham", "leeds", "edinburgh", "glasgow", "bristol",
]

def generate_job_id(company, title):
    raw_str = f"{company.lower().strip()}_{title.lower().strip()}"
    return hashlib.md5(raw_str.encode("utf-8")).hexdigest()

def clean_text(raw_html):
    cleanr = re.compile("<.*?>")
    cleantext = re.sub(cleanr, " ", raw_html)
    return " ".join(cleantext.lower().split())


def contains_location_marker(text, markers):
    return any(re.search(rf"\b{re.escape(marker)}\b", text) for marker in markers)

def is_relevant_job(title, description, location=""):
    title_clean = clean_text(title)
    desc_clean = clean_text(description)
    loc_clean = clean_text(location)
    
    # Prefer the source location so a London location in a description cannot
    # make an unrelated job look eligible.
    combined_text = f"{title_clean} {desc_clean} {loc_clean}"
    location_text = loc_clean or combined_text
    if contains_location_marker(location_text, NON_BELGIAN_LOCATIONS):
        return False
    if not contains_location_marker(location_text, ALLOWED_LOCATIONS):
        return False

    # 2. SENIORITY CHECK: Reject Senior, Director, Lead, VP roles
    if any(ex in title_clean for ex in EXCLUDE_TITLE_KEYWORDS):
        return False
        
    # 3. SCOPE CHECK: Ensure the job title/desc matches Data/BI roles
    has_tech_match = any(keyword in combined_text for keyword in TARGET_KEYWORDS)
    has_entry_signal = any(keyword in combined_text for keyword in ENTRY_LEVEL_KEYWORDS)
    has_allowed_experience = bool(EXPERIENCE_PATTERN.search(combined_text))
    
    return has_tech_match and (has_entry_signal or has_allowed_experience)

def save_jobs_to_db(jobs, source_type):
    new_jobs_count = 0
    duplicate_count = 0
    filtered_count = 0
    discovered_at = datetime.now(timezone.utc).isoformat()
    
    with sqlite3.connect("jobs.db") as conn:
        for item in jobs:
            title = item.get("title", "") or ""
            company = item.get("company_name", "") or item.get("company", "") or "Unknown"
            description = item.get("description", "") or ""
            location = item.get("location", "") or ""
            
            if not title or not is_relevant_job(title, description, location):
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
            
            try:
                conn.execute(
                    """INSERT INTO jobs
                    (id, title, company, location, url, source, description,
                     category, contract_type, salary_min, salary_max,
                     salary_currency, posted_at, discovered_at, source_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (job_id, title, company, location, job_url, source_type,
                     description, category, contract_type, salary_min, salary_max,
                     salary_currency, posted_at, discovered_at, json.dumps(item, default=str)),
                )
                new_jobs_count += 1
            except sqlite3.IntegrityError:
                duplicate_count += 1
                continue

    print(f"🎯 [{source_type}] Saved {new_jobs_count} job(s) | ({duplicate_count} duplicates, {filtered_count} filtered)")

def fetch_arbeitnow_jobs(keyword="data"):
    """Fetch Arbeitnow listings and apply the same Belgian eligibility gate."""
    url = "https://www.arbeitnow.com/api/job-board-api"
    print(f"🔍 Searching Arbeitnow for '{keyword}' jobs...")
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        jobs = response.json().get("data", [])
        save_jobs_to_db(jobs, "Arbeitnow")
    except (requests.RequestException, ValueError) as error:
        print(f"❌ Arbeitnow error: {error}")

def fetch_adzuna_belgium(keyword="data engineer", location="belgium", page=1):
    """Fetches jobs specifically from Adzuna Belgium API."""
    app_id = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_APP_KEY")
    if not app_id or not app_key or "your_app" in app_id:
        print("⚠️ Adzuna credentials missing in .env (skipping Adzuna)")
        return

    url = f"https://api.adzuna.com/v1/api/jobs/be/search/{page}"
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": 50,
        "what": keyword,
        "where": location
    }
    print(f"🔍 Searching Adzuna (BE) for '{keyword}' near '{location}'...")
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        results = response.json().get("results", [])
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
        save_jobs_to_db(formatted_jobs, "Adzuna Belgium")
    except (requests.RequestException, ValueError) as error:
        print(f"❌ Adzuna BE error: {error}")

def run_discovery():
    init_db()
    print("🇧🇪 Executing Targeted Belgian Job Discovery...\n")
    
    # Target Junior, Traineeship, and Entry-level searches in Belgium
    fetch_adzuna_belgium(keyword="junior data engineer", location="belgium")
    fetch_adzuna_belgium(keyword="junior bi analyst", location="brussels")
    fetch_adzuna_belgium(keyword="data traineeship", location="belgium")
    fetch_adzuna_belgium(keyword="junior power bi", location="antwerp")
    fetch_adzuna_belgium(keyword="data analyst entry level", location="mechelen")
    fetch_arbeitnow_jobs()

if __name__ == "__main__":
    run_discovery()