import hashlib
import os
import sqlite3

import requests
from dotenv import load_dotenv

from database import init_db

load_dotenv()

TARGET_KEYWORDS = [
    "data engineer", "bi analyst", "business intelligence", "databricks",
    "pyspark", "fabric", "power bi", "data integration", "etl",
    "data platform", "analytics engineer",
]
EXCLUDE_KEYWORDS = ["marketing", "media", "sales", "hr", "recruiter", "designer"]


def generate_job_id(company, title):
    raw_str = f"{company.lower().strip()}_{title.lower().strip()}"
    return hashlib.md5(raw_str.encode("utf-8")).hexdigest()


def is_relevant_job(title, description):
    title_lower = title.lower()
    description_lower = description.lower()
    if any(keyword in title_lower for keyword in EXCLUDE_KEYWORDS):
        return False
    return any(
        keyword in title_lower or keyword in description_lower
        for keyword in TARGET_KEYWORDS
    )


def save_jobs_to_db(jobs, source_type):
    new_jobs_count = 0
    with sqlite3.connect("jobs.db") as conn:
        for item in jobs:
            title = item.get("title", "") or ""
            company = item.get("company_name", "") or ""
            description = item.get("description", "") or ""
            if not title or not is_relevant_job(title, description):
                continue

            job_id = generate_job_id(company, title)
            location = item.get("location", "Remote/Unspecified") or "Remote/Unspecified"
            job_url = item.get("url", "") or ""
            try:
                conn.execute(
                    "INSERT INTO jobs (id, title, company, location, url, source) VALUES (?, ?, ?, ?, ?, ?)",
                    (job_id, title, company, location, job_url, source_type),
                )
                new_jobs_count += 1
            except sqlite3.IntegrityError:
                continue

    print(f"🎯 [{source_type}] Saved {new_jobs_count} new relevant job(s) to jobs.db")


def fetch_arbeitnow_jobs(keyword="data"):
    url = "https://www.arbeitnow.com/api/job-board-api"
    print(f"🔍 Searching Arbeitnow for '{keyword}' jobs...")
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        save_jobs_to_db(response.json().get("data", []), "Arbeitnow")
    except (requests.RequestException, ValueError) as error:
        print(f"❌ Arbeitnow error: {error}")


def fetch_adzuna_jobs(country="be", keyword="data engineer", page=1):
    app_id = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        print("⚠️ Adzuna credentials missing in .env (skipping Adzuna)")
        return

    url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": 20,
        "what": keyword,
    }
    print(f"🔍 Searching Adzuna ({country}) for '{keyword}' jobs...")
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        results = response.json().get("results", [])
        formatted_jobs = [
            {
                "title": result.get("title", ""),
                "company_name": result.get("company", {}).get("display_name", ""),
                "description": result.get("description", ""),
                "location": result.get("location", {}).get("display_name", "Belgium"),
                "url": result.get("redirect_url", ""),
            }
            for result in results
        ]
        save_jobs_to_db(formatted_jobs, "Adzuna")
    except (requests.RequestException, ValueError) as error:
        print(f"❌ Adzuna error: {error}")


def run_discovery():
    init_db()
    print("🔍 Searching across multiple job platforms...")
    fetch_arbeitnow_jobs()
    fetch_adzuna_jobs(keyword="data engineer")
    fetch_adzuna_jobs(keyword="power bi")


if __name__ == "__main__":
    run_discovery()