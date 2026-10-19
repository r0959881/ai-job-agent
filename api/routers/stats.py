"""Dashboard numbers."""
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request

import agent_settings
from api import db
from api.services import integrations
from api.services.jobs import HAS_CV_SQL, POSTED_SQL, job_row
from api.services.runs import events_path_for, read_events_file, row_to_run

router = APIRouter(prefix="/api", tags=["stats"])
APPLIED = "('applied', 'interviewing', 'offer', 'rejected')"


@router.get("/stats")
def stats(request: Request):
    window = agent_settings.get("time_window_hours")
    since = (datetime.now(UTC) - timedelta(hours=window)).isoformat()
    count = lambda sql, params=(): db.one_row(sql, params)["n"]  # noqa: E731
    total = count("SELECT COUNT(*) AS n FROM jobs")
    eligible = count("SELECT COUNT(*) AS n FROM jobs WHERE status != 'rejected'")
    tailored = count(f"SELECT COUNT(*) AS n FROM jobs j WHERE {HAS_CV_SQL}")
    applied = count(f"SELECT COUNT(*) AS n FROM jobs WHERE application_status IN {APPLIED} AND applied_at != ''")
    interviewing = count("SELECT COUNT(*) AS n FROM jobs WHERE application_status IN ('interviewing', 'offer')")

    last = db.one_row("SELECT * FROM runs ORDER BY id DESC LIMIT 1")
    last_run = None
    if last:
        runs = request.app.state.runs
        events = runs.events(last["id"])[0] if runs.recent.get(last["id"]) else read_events_file(events_path_for(last["id"]))
        last_run = row_to_run(last, events)

    ready = db.all_rows(
        f"""SELECT j.*, {HAS_CV_SQL} AS has_cv FROM jobs j
        WHERE {HAS_CV_SQL} AND COALESCE(j.application_status, 'not_applied') = 'not_applied'
        ORDER BY {POSTED_SQL} DESC LIMIT 8"""
    )
    return {
        "jobs_last_window": count(f"SELECT COUNT(*) AS n FROM jobs j WHERE {POSTED_SQL} >= ?", (since,)),
        "window_hours": window,
        "cvs_generated": count("SELECT COUNT(*) AS n FROM documents WHERE kind = 'cv'"),
        "applications_sent": applied,
        "interviews": interviewing,
        "funnel": [
            {"key": "discovered", "label": "Discovered", "count": total},
            {"key": "eligible", "label": "Eligible", "count": eligible},
            {"key": "tailored", "label": "CV tailored", "count": tailored},
            {"key": "applied", "label": "Applied", "count": applied},
            {"key": "interviewing", "label": "Interviewing", "count": interviewing},
        ],
        "last_run": last_run,
        "ready_to_apply": [job_row(r) for r in ready],
        "integrations": integrations.status(),
    }
