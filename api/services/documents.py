"""Keep the documents table in sync with the files in output/."""
from datetime import UTC, datetime

from config import OUTPUT_DIR, RUNS_DIR, load_resume_file, relative_to_project, resolve_project_path
from database import init_db, transaction
from discovery import classify_target_role, get_target_roles
from report import cv_prefix_for_job

DOCUMENT_SUFFIXES = {".docx", ".xlsx", ".txt", ".pdf"}


def _safe_role(role):
    return "".join(c for c in role if c.isalnum() or c in " _-").strip()


def normalise(path):
    """Stored paths may use either slash or be absolute; compare them as 'output/x'."""
    return relative_to_project(resolve_project_path(str(path).replace("\\", "/")))


def classify_file(name, role_names):
    """Return (kind, role_family) from a generated file name."""
    lower = name.lower()
    if lower.endswith(".xlsx") and lower.startswith("job_report"):
        return "report", ""
    if "_cover_letter_" in lower:
        tail = name.split("_Cover_Letter_", 1)[-1].rsplit(".", 1)[0]
        for role in role_names:
            if tail == _safe_role(role):
                return "cover_letter", role
        return "cover_letter", ""
    if "_cv_" in lower and lower.endswith(".docx"):
        tail = name.rsplit(".", 1)[0].rsplit("_", 1)[-1]
        return "cv", next((role for role in role_names if tail == _safe_role(role)), "")
    return "other", ""


def backfill_documents(db_path=None):
    """Scan output/, add missing documents rows, link CVs to jobs, drop rows for deleted files.

    Returns counts {"added", "removed", "linked", "role_families"}.
    """
    init_db(db_path, quiet=True)
    full_name = ((load_resume_file() or {}).get("personal_info") or {}).get("full_name") or ""
    role_names = list(get_target_roles())
    counts = {"added": 0, "removed": 0, "linked": 0, "role_families": 0}
    with transaction(db_path) as conn:
        conn.row_factory = None
        jobs = conn.execute(
            "SELECT id, title, company, cv_path, cover_letter_path, role_family FROM jobs"
        ).fetchall()
        family_by_job = {row[0]: row[5] or classify_target_role(row[1] or "") or "" for row in jobs}
        by_cv_path = {}
        prefixes = []
        for job_id, title, company, cv_path, cover_path, role_family in jobs:
            for stored in (cv_path, cover_path):
                if stored:
                    by_cv_path[normalise(stored)] = job_id
            prefix = cv_prefix_for_job({"title": title, "company": company}, full_name=full_name)
            prefixes.append((prefix, job_id))
            if not role_family:
                family = classify_target_role(title or "")
                if family:
                    conn.execute("UPDATE jobs SET role_family = ? WHERE id = ?", (family, job_id))
                    counts["role_families"] += 1
        prefixes.sort(key=lambda item: len(item[0]), reverse=True)

        existing = {row[0]: row for row in conn.execute("SELECT path, id, job_id FROM documents")}
        seen = set()
        if OUTPUT_DIR.exists():
            for file in sorted(OUTPUT_DIR.iterdir()):
                if not file.is_file() or file.suffix.lower() not in DOCUMENT_SUFFIXES or file.name.startswith("~$"):
                    continue
                path = relative_to_project(file)
                seen.add(path)
                kind, role_family = classify_file(file.name, role_names)
                job_id = by_cv_path.get(path)
                if job_id is None and kind == "cv":
                    job_id = next((jid for prefix, jid in prefixes if file.name.startswith(prefix)), None)
                created = datetime.fromtimestamp(file.stat().st_mtime, UTC).isoformat()
                if path in existing:
                    if job_id and not existing[path][2]:
                        conn.execute("UPDATE documents SET job_id = ? WHERE path = ?", (job_id, path))
                        counts["linked"] += 1
                    continue
                if kind == "cv" and job_id:
                    role_family = family_by_job.get(job_id) or role_family
                conn.execute(
                    "INSERT INTO documents (job_id, kind, role_family, path, created_at) VALUES (?, ?, ?, ?, ?)",
                    (job_id, kind, role_family, path, created),
                )
                counts["added"] += 1
                counts["linked"] += bool(job_id)
        for path in set(existing) - seen:
            if not path.startswith(relative_to_project(RUNS_DIR)):
                conn.execute("DELETE FROM documents WHERE path = ?", (path,))
                counts["removed"] += 1
    return counts

