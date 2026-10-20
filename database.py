import contextlib
import sqlite3

import agent_settings
from agent_log import log
from config import DB_PATH

JOB_COLUMNS = {
    "description": "TEXT DEFAULT ''",
    "category": "TEXT DEFAULT ''",
    "contract_type": "TEXT DEFAULT ''",
    "salary_min": "REAL",
    "salary_max": "REAL",
    "salary_currency": "TEXT DEFAULT ''",
    "posted_at": "TEXT DEFAULT ''",
    "discovered_at": "TEXT DEFAULT ''",
    "cv_path": "TEXT DEFAULT ''",
    "source_data": "TEXT DEFAULT ''",
    "role_family": "TEXT DEFAULT ''",
    "application_status": "TEXT DEFAULT 'not_applied'",
    "applied_at": "TEXT DEFAULT ''",
    "notes": "TEXT DEFAULT ''",
    "cover_letter_path": "TEXT DEFAULT ''",
    "follow_up_at": "TEXT DEFAULT ''",
    "apply_checklist": "TEXT DEFAULT ''",
}

RUN_COLUMNS = {
    "started_at": "TEXT DEFAULT ''",
    "finished_at": "TEXT DEFAULT ''",
    "status": "TEXT DEFAULT 'running'",
    "discovered": "INTEGER DEFAULT 0",
    "new": "INTEGER DEFAULT 0",
    "filtered": "INTEGER DEFAULT 0",
    "tailored": "INTEGER DEFAULT 0",
    "failed": "INTEGER DEFAULT 0",
    "error": "TEXT DEFAULT ''",
    "log_path": "TEXT DEFAULT ''",
    "options": "TEXT DEFAULT ''",
    "summary": "TEXT DEFAULT ''",
}

DOCUMENT_COLUMNS = {
    "job_id": "TEXT",
    "kind": "TEXT DEFAULT 'cv'",
    "role_family": "TEXT DEFAULT ''",
    "path": "TEXT DEFAULT ''",
    "created_at": "TEXT DEFAULT ''",
    "run_id": "INTEGER",
}

# Kept as fallbacks; the effective lists come from agent_settings.yaml.
NON_BELGIAN_LOCATION_MARKERS = tuple(agent_settings.DEFAULTS["blocked_locations"])
ALLOWED_LOCATION_MARKERS = tuple(agent_settings.DEFAULTS["allowed_locations"])


def connect(path=None):
    connection = sqlite3.connect(path or DB_PATH, timeout=30)
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


@contextlib.contextmanager
def transaction(path=None):
    """Commit on success, roll back on error, and always close (Windows keeps open files locked)."""
    connection = connect(path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _add_missing_columns(cursor, table, columns):
    existing_columns = {row[1] for row in cursor.execute(f"PRAGMA table_info({table})")}
    for column, definition in columns.items():
        if column not in existing_columns:
            cursor.execute(f'ALTER TABLE {table} ADD COLUMN "{column}" {definition}')


def init_db(path=None, quiet=False):
    conn = connect(path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            title TEXT,
            company TEXT,
            location TEXT,
            url TEXT,
            source TEXT,
            status TEXT DEFAULT 'new'
        )
    ''')
    _add_missing_columns(cursor, "jobs", JOB_COLUMNS)
    cursor.execute("CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY AUTOINCREMENT)")
    _add_missing_columns(cursor, "runs", RUN_COLUMNS)
    cursor.execute("CREATE TABLE IF NOT EXISTS documents (id INTEGER PRIMARY KEY AUTOINCREMENT)")
    _add_missing_columns(cursor, "documents", DOCUMENT_COLUMNS)
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS documents_path ON documents(path)")
    cursor.execute(
        "UPDATE jobs SET discovered_at = datetime('now') "
        "WHERE COALESCE(discovered_at, '') = ''"
    )
    # Jobs are filtered by location when they are saved (discovery.is_relevant_job), per run and
    # region, so nothing is deleted here: a German or remote job from one run must survive the next save.
    conn.commit()
    conn.close()
    if not quiet:
        log("✅ Database initialized successfully!")


def record_document(path, kind, job_id=None, role_family="", run_id=None, db_path=None):
    """Insert or refresh a documents row for a generated file (path as stored, e.g. output/x.docx)."""
    from datetime import datetime, timezone

    with transaction(db_path) as conn:
        conn.execute(
            """INSERT INTO documents (job_id, kind, role_family, path, created_at, run_id)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                job_id = COALESCE(excluded.job_id, documents.job_id),
                kind = excluded.kind,
                role_family = CASE WHEN excluded.role_family = '' THEN documents.role_family ELSE excluded.role_family END,
                created_at = excluded.created_at,
                run_id = COALESCE(excluded.run_id, documents.run_id)""",
            (job_id, kind, role_family or "", path, datetime.now(timezone.utc).isoformat(), run_id),
        )


if __name__ == "__main__":
    init_db()
