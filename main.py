from datetime import datetime, timedelta, timezone
import sqlite3

import agent_settings
import languages
from agent_log import check_cancelled, event_scope, log, step
from config import DB_PATH
from database import init_db, record_document, transaction
from discovery import DISCOVERY_SOURCES, classify_target_role, is_relevant_job, run_discovery, run_scope
from gmail_parser import GmailAuthRequired, parse_email_alerts
from tailor import GroqConfigError, check_groq_key, describe_error, get_client, tailor_cv_for_job
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


def role_of(job, settings):
    """Stored role family, or one inferred from the title and description for older rows."""
    return job["role_family"] or classify_target_role(job["title"], job["description"] or "", settings=settings)


def refresh_job_statuses(jobs, settings=None):
    """Re-evaluate old rows using the complete stored description."""
    settings = settings or agent_settings.load()
    eligible_ids = [
        job["id"] for job in jobs
        if is_relevant_job(job["title"], job["description"], job["location"], settings=settings)
    ]
    with transaction() as connection:
        connection.executemany(
            "UPDATE jobs SET status = 'new' WHERE id = ? AND status = 'rejected'",
            [(job_id,) for job_id in eligible_ids],
        )
    return set(eligible_ids)


def _run_gmail(interactive, settings=None):
    step("gmail", "started", "Reading Gmail job alerts")
    try:
        counts = parse_email_alerts(interactive=interactive, settings=settings)
    except GmailAuthRequired as error:
        log(f"⚠️ Gmail skipped: {error.reason}", level="warning")
        step("gmail", "warning", error.reason, {"action": "reconnect_gmail", "gmail_status": error.status})
        return None
    if counts is None:
        step("gmail", "warning", "Gmail alerts could not be read. See the log for details.")
    else:
        step("gmail", "succeeded",
             f"{counts['messages']} alert emails, {counts['new']} new jobs, {counts['filtered']} filtered", counts)
    return counts


def run_agent(on_event=None, options=None, cancel_event=None, run_id=None, interactive=True):
    """Run the full pipeline.

    on_event(step, status, message, data) receives progress events; options can
    contain sources (list), regions (region ids), roles (role names), languages
    (language ids), time_window_hours, max_tailor and dry_run. Without regions
    the default regions from the settings are searched; without roles every
    target role is; without languages the default languages are kept (an empty
    list keeps every language).
    Returns a summary dict with counts and the report path.
    """
    with event_scope(on_event, cancel_event):
        return _run_agent(options or {}, run_id, interactive)


def _run_agent(options, run_id, interactive):
    window_hours = int(options.get("time_window_hours") or agent_settings.get("time_window_hours"))
    roles = options.get("roles")
    job_languages = options.get("languages")
    if job_languages is None:
        job_languages = agent_settings.get("languages")
    settings, search_context = run_scope(agent_settings.load(), options.get("regions"), roles, window_hours)
    enabled = {name for name, on in settings["sources"].items() if on}
    sources = set(options["sources"]) if options.get("sources") is not None else enabled
    max_tailor = options.get("max_tailor")
    dry_run = bool(options.get("dry_run"))
    summary = {"discovered": 0, "new": 0, "filtered": 0, "tailored": 0, "failed": 0,
               "eligible": 0, "failures": [], "report_path": "", "sources": {}}

    run_time = datetime.now(timezone.utc)
    cutoff = run_time - timedelta(hours=window_hours)
    log(f"🚀 Running AI Job Agent Pipeline at {run_time.isoformat()}\n")

    # 1. Initialize SQLite Database
    step("init_db", "started", "Preparing the jobs database")
    init_db()
    step("init_db", "succeeded", "Database ready")
    check_cancelled()

    # 2. Discover jobs in the chosen regions across scrapers, job APIs and Gmail alerts
    discovered = run_discovery(sources=sources & DISCOVERY_SOURCES, settings=settings, ctx=search_context)
    for key in ("discovered", "new", "filtered"):
        summary[key] += discovered[key]
    check_cancelled()
    if "gmail" in sources:
        gmail_counts = _run_gmail(interactive, settings)
        if gmail_counts:
            for key in ("discovered", "new", "filtered"):
                summary[key] += gmail_counts[key]
            summary["sources"]["gmail"] = gmail_counts
    else:
        step("gmail", "skipped", "Gmail is turned off for this run.")
    check_cancelled()

    # 3. Select eligible jobs posted or seen in the last 48 hours.
    step("filter", "started", f"Selecting eligible jobs from the last {window_hours} hours")
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    jobs = conn.execute(
        "SELECT * FROM jobs"
    ).fetchall()
    conn.close()

    eligible_ids = refresh_job_statuses(jobs, settings)

    in_scope = [
        dict(job) for job in jobs
        if is_recent_job(job["posted_at"], job["discovered_at"], cutoff)
        and job["id"] in eligible_ids
        and (roles is None or role_of(job, settings) in roles)
    ]
    language_reasons = {}
    for job in in_scope:
        keep, reason = languages.check_job(job["title"], job["description"], job_languages)
        if not keep:
            language_reasons[job["id"]] = reason
    recent_jobs = [job for job in in_scope if job["id"] not in language_reasons]
    if language_reasons:
        log(f"🌐 {len(language_reasons)} job(s) skipped because of their language.")
    recent_ids = {job["id"] for job in recent_jobs}
    excluded_jobs = [dict(job) for job in jobs if job["id"] not in recent_ids]
    for job in excluded_jobs:
        job["exclusion_reason"] = language_reasons.get(job["id"]) or (
            f"Outside {window_hours}-hour window, the selected regions or roles, or the eligibility filter")
    summary["eligible"] = len(recent_jobs)
    summary["language_filtered"] = len(language_reasons)
    message = f"{len(recent_jobs)} eligible of {len(jobs)} stored jobs"
    if language_reasons:
        message += f", {len(language_reasons)} skipped for language"
    step("filter", "succeeded", message,
         {"eligible": len(recent_jobs), "total": len(jobs), "language_filtered": len(language_reasons)})

    to_tailor = [job for job in recent_jobs if not job.get("cv_path")]
    if max_tailor is not None:
        to_tailor = to_tailor[: int(max_tailor)]
    client = None
    if dry_run:
        step("tailoring", "skipped", "Dry run: no CVs were tailored.")
    elif to_tailor:
        try:
            check_groq_key()
            client = get_client()
        except GroqConfigError as error:
            log(str(error), level="warning")
            step("tailoring", "skipped", "GROQ_API_KEY is missing or invalid, so no CVs were tailored.",
                 {"action": "configure_groq"})
        if client:
            step("tailoring", "started", f"Tailoring {len(to_tailor)} CV(s)", {"done": 0, "total": len(to_tailor)})
    else:
        step("tailoring", "succeeded", "Every eligible job already has a CV.", {"done": 0, "total": 0})

    tailor_ids = {job["id"] for job in to_tailor}
    done = 0
    for job in recent_jobs:
        if not job.get("cv_path") and client and job["id"] in tailor_ids:
            check_cancelled()
            log(f"\n⚡ Tailoring CV: {job['title']} at {job['company']}")
            try:
                job["cv_path"] = tailor_cv_for_job(job["id"], client=client, run_id=run_id, raise_errors=True) or ""
            except Exception as error:
                job["cv_path"] = ""
                summary["failures"].append({"job_id": job["id"], "title": job["title"], "reason": describe_error(error)})
            done += 1
            if job["cv_path"]:
                summary["tailored"] += 1
            elif not summary["failures"] or summary["failures"][-1]["job_id"] != job["id"]:
                summary["failures"].append({"job_id": job["id"], "title": job["title"], "reason": "No CV was produced"})
            step("tailoring", "progress", f"Tailored {done} of {len(to_tailor)}",
                 {"done": done, "total": len(to_tailor), "job_id": job["id"], "ok": bool(job["cv_path"])})
        if not job.get("cv_path"):
            job["cv_path"] = find_existing_cv(job)
    summary["failed"] = len(summary["failures"])
    if client:
        message = f"Tailored {summary['tailored']} of {len(to_tailor)} CVs."
        if summary["failures"]:
            reasons = sorted({failure["reason"] for failure in summary["failures"]})
            message += f" {summary['failed']} failed: {'; '.join(reasons)}."
        step("tailoring", "warning" if summary["failures"] else "succeeded", message,
             {"done": done, "total": len(to_tailor), "failures": summary["failures"]})
    check_cancelled()

    step("report", "started", "Writing the Excel report")
    report_path = (
        f"output/job_report_{run_time.strftime('%Y%m%d_%H%M%S')}.xlsx"
    )
    export_jobs_to_excel(recent_jobs, report_path, excluded_jobs)
    record_document(report_path, "report", run_id=run_id)
    summary["report_path"] = report_path
    log(f"📊 Excel report created: {report_path}")
    log(f"✅ Included {len(recent_jobs)} eligible job(s) from the last {window_hours} hours.")
    step("report", "succeeded", f"Report saved with {len(recent_jobs)} jobs", {"path": report_path})
    return summary


def cli():
    """`python run_agent.py`: exit early with the friendly message when Groq is not configured."""
    try:
        check_groq_key()
    except GroqConfigError as error:
        raise SystemExit(str(error))
    run_agent()


if __name__ == "__main__":
    cli()
