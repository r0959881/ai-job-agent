from datetime import datetime, timedelta, timezone
import sqlite3
from database import init_db
from discovery import run_discovery
from discovery import is_relevant_job
from gmail_parser import parse_email_alerts
from tailor import tailor_cv_for_job
from report import export_jobs_to_excel, find_existing_cv


def parse_job_datetime(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def is_recent_job(posted_at, discovered_at, cutoff):
    job_date = parse_job_datetime(posted_at) or parse_job_datetime(discovered_at)
    return job_date is not None and job_date >= cutoff


def refresh_job_statuses(jobs):
    """Re-evaluate old rows using the complete stored description."""
    eligible_ids = [
        job["id"] for job in jobs
        if is_relevant_job(job["title"], job["description"], job["location"])
    ]
    with sqlite3.connect("jobs.db") as connection:
        connection.executemany(
            "UPDATE jobs SET status = 'new' WHERE id = ? AND status = 'rejected'",
            [(job_id,) for job_id in eligible_ids],
        )
    return set(eligible_ids)

def run_agent():
    run_time = datetime.now(timezone.utc)
    cutoff = run_time - timedelta(hours=48)
    print(f"🚀 Running AI Job Agent Pipeline at {run_time.isoformat()}\n")
    
    # 1. Initialize SQLite Database
    init_db()
    
    # 2. Discover & Ingest Belgian jobs across APIs and Gmail alerts
    run_discovery()
    parse_email_alerts()
    
    # 3. Select eligible jobs posted or seen in the last 48 hours.
    conn = sqlite3.connect("jobs.db")
    conn.row_factory = sqlite3.Row
    jobs = conn.execute(
        "SELECT * FROM jobs"
    ).fetchall()
    conn.close()

    eligible_ids = refresh_job_statuses(jobs)

    recent_jobs = [
        dict(job) for job in jobs
        if is_recent_job(job["posted_at"], job["discovered_at"], cutoff)
        and job["id"] in eligible_ids
    ]
    excluded_jobs = [dict(job) for job in jobs if dict(job) not in recent_jobs]
    for job in excluded_jobs:
        job["exclusion_reason"] = "Outside 48-hour window or eligibility filter"

    for job in recent_jobs:
        if not job.get("cv_path"):
            print(f"\n⚡ Tailoring CV: {job['title']} at {job['company']}")
            job["cv_path"] = tailor_cv_for_job(job["id"]) or ""
        if not job.get("cv_path"):
            job["cv_path"] = find_existing_cv(job)

    report_path = (
        f"output/job_report_{run_time.strftime('%Y%m%d_%H%M%S')}.xlsx"
    )
    export_jobs_to_excel(recent_jobs, report_path, excluded_jobs)
    print(f"📊 Excel report created: {report_path}")
    print(f"✅ Included {len(recent_jobs)} eligible job(s) from the last 48 hours.")

if __name__ == "__main__":
    run_agent()