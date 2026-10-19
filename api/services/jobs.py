"""Job queries and per-job actions (tailor, cover letter, auto-fill) for the API."""
import json
import os
import queue
import re
import subprocess
import sys
import threading
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException

from api import db
from api.services.documents import document_row
from config import CODE_ROOT, resolve_project_path
from database import record_document

APPLICATION_STATUSES = ["not_applied", "applied", "interviewing", "offer", "rejected", "skipped"]
CHECKLIST_KEYS = ["review", "cv", "cover_letter", "answers", "apply", "track"]

HAS_CV_SQL = ("(COALESCE(j.cv_path, '') != '' OR EXISTS (SELECT 1 FROM documents d "
              "WHERE d.job_id = j.id AND d.kind = 'cv'))")
POSTED_SQL = "COALESCE(NULLIF(j.posted_at, ''), j.discovered_at)"
SORTS = {
    "title": "j.title COLLATE NOCASE",
    "company": "j.company COLLATE NOCASE",
    "location": "j.location COLLATE NOCASE",
    "role_family": "j.role_family",
    "source": "j.source",
    "posted": POSTED_SQL,
    "discovered": "j.discovered_at",
    "status": "j.status",
    "application_status": "j.application_status",
    "has_cv": HAS_CV_SQL,
    "salary": "COALESCE(j.salary_max, j.salary_min)",
}


def now_iso():
    return datetime.now(UTC).isoformat()


def job_row(row):
    job = dict(row)
    job.pop("source_data", None)
    try:
        job["apply_checklist"] = json.loads(job.get("apply_checklist") or "{}")
    except ValueError:
        job["apply_checklist"] = {}
    job["application_status"] = job.get("application_status") or "not_applied"
    job["has_cv"] = bool(job.get("has_cv"))
    for key in ("role_family", "notes", "applied_at", "follow_up_at", "cover_letter_path", "cv_path"):
        job[key] = job.get(key) or ""
    return job


def list_jobs(params):
    clauses, args = [], []
    if params.get("q"):
        clauses.append("(j.title LIKE ? OR j.company LIKE ? OR j.location LIKE ? OR j.description LIKE ?)")
        args += [f"%{params['q']}%"] * 4
    for key in ("status", "application_status", "role_family"):
        values = params.get(key) or []
        if values:
            clauses.append(f"COALESCE(j.{key}, '') IN ({', '.join('?' for _ in values)})")
            args += values
    if params.get("source"):
        clauses.append("(" + " OR ".join("j.source LIKE ?" for _ in params["source"]) + ")")
        args += [f"%{source}%" for source in params["source"]]
    if params.get("date_from"):
        clauses.append(f"{POSTED_SQL} >= ?")
        args.append(params["date_from"])
    if params.get("date_to"):
        clauses.append(f"{POSTED_SQL} < ?")
        args.append(params["date_to"] + "T23:59:59.999" if len(params["date_to"]) == 10 else params["date_to"])
    if params.get("has_cv") is not None:
        clauses.append(HAS_CV_SQL if params["has_cv"] else f"NOT {HAS_CV_SQL}")
    quick = params.get("quick")
    if quick == "ready":
        clauses.append(f"{HAS_CV_SQL} AND COALESCE(j.application_status, 'not_applied') = 'not_applied'")
    elif quick == "applied_week":
        clauses.append("j.applied_at >= ?")
        args.append((datetime.now(UTC) - timedelta(days=7)).isoformat())
    elif quick == "follow_up":
        clauses.append("j.follow_up_at != '' AND j.follow_up_at <= ?")
        args.append(datetime.now(UTC).date().isoformat() + "T23:59:59")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    sort = SORTS.get(params.get("sort") or "posted", SORTS["posted"])
    order = "ASC" if params.get("order") == "asc" else "DESC"
    page = max(1, int(params.get("page") or 1))
    size = max(1, min(int(params.get("page_size") or 50), 500))
    total = db.one_row(f"SELECT COUNT(*) AS n FROM jobs j {where}", tuple(args))["n"]
    rows = db.all_rows(
        f"""SELECT j.*, {HAS_CV_SQL} AS has_cv FROM jobs j {where}
        ORDER BY {sort} {order}, j.id LIMIT ? OFFSET ?""",
        (*args, size, (page - 1) * size),
    )
    facets = {
        "sources": sorted({part.strip() for r in db.all_rows("SELECT DISTINCT source FROM jobs")
                           for part in (r["source"] or "").split("|") if part.strip()}),
        "role_families": [r["role_family"] for r in db.all_rows(
            "SELECT DISTINCT role_family FROM jobs WHERE COALESCE(role_family, '') != '' ORDER BY role_family")],
    }
    return {"items": [job_row(r) for r in rows], "total": total, "page": page, "page_size": size, "facets": facets}


def get_job_or_404(job_id):
    row = db.one_row(f"SELECT j.*, {HAS_CV_SQL} AS has_cv FROM jobs j WHERE j.id = ?", (job_id,))
    if not row:
        raise HTTPException(404, "That job no longer exists. It may have been deleted or filtered out.")
    return job_row(row)


def _words_in(text, keyword):
    return re.search(rf"(?<![\w]){re.escape(keyword.lower())}(?![\w])", text) is not None


def keyword_match(job, resume):
    """Resume keywords found in the posting, and the role keywords it does not mention."""
    text = f"{job.get('title', '')} {job.get('description', '')}".lower()
    profile = (resume.get("role_profiles") or {}).get(job.get("role_family") or "", {})
    role_keywords = list(profile.get("keywords") or [])
    skills = [skill for skills in (resume.get("core_skills") or {}).values() for skill in skills]
    candidates: list[str] = []
    for keyword in role_keywords + skills:
        short = re.sub(r"\s*\(.*?\)", "", keyword).strip()
        if short and short.lower() not in {c.lower() for c in candidates}:
            candidates.append(short)
    matched = [k for k in candidates if _words_in(text, k)]
    missing = [k for k in role_keywords if not _words_in(text, re.sub(r"\s*\(.*?\)", "", k).strip())]
    return matched, missing


def source_tips(job):
    source = (job.get("source") or "").lower()
    tips = []
    if "linkedin" in source:
        tips.append("LinkedIn alert links open LinkedIn: sign in first. “Easy Apply” means you upload your CV "
                    "in LinkedIn's own dialog, so download the tailored CV below first.")
    if "indeed" in source:
        tips.append("Indeed may ask you to sign in. “Easily apply” uses Indeed's form: upload the tailored CV there.")
    if "adzuna" in source:
        tips.append("Adzuna links redirect to the employer or agency site. Apply on the page you land on.")
    if "arbeitnow" in source:
        tips.append("Arbeitnow listings link to the company's careers page, which often has its own form.")
    if "stepstone" in source or "jobat" in source:
        tips.append("StepStone and Jobat usually need an account; your CV upload there can be reused for later jobs.")
    if "vdab" in source:
        tips.append("VDAB vacancies may require applying through your Mijn Loopbaan account.")
    if "actiris" in source:
        tips.append("Actiris links may need you to sign in to My Actiris first.")
    if (job.get("company") or "").startswith("Partner ("):
        tips.append("The company name was not in the alert email. Open the posting to find it before you write "
                    "the cover letter.")
    return tips


def job_detail(job_id):
    from config import load_resume_file

    job = get_job_or_404(job_id)
    row = db.one_row("SELECT description FROM jobs WHERE id = ?", (job_id,))
    job["description"] = (row or {}).get("description") or ""
    docs = db.all_rows(
        "SELECT d.*, j.title AS job_title, j.company AS job_company FROM documents d "
        "LEFT JOIN jobs j ON j.id = d.job_id WHERE d.job_id = ? ORDER BY d.created_at DESC",
        (job_id,),
    )
    job["documents"] = [document_row(d) for d in docs]
    cv_docs = [d for d in job["documents"] if d["kind"] == "cv" and d["exists"]]
    if not job["cv_path"] or not resolve_project_path(job["cv_path"]).exists():
        job["cv_path"] = cv_docs[0]["path"] if cv_docs else ""
    letters = [d for d in job["documents"] if d["kind"] == "cover_letter" and d["exists"]]
    if not job["cover_letter_path"] or not resolve_project_path(job["cover_letter_path"]).exists():
        job["cover_letter_path"] = letters[0]["path"] if letters else ""
    resume = load_resume_file() or {}
    job["matched_keywords"], job["missing_keywords"] = keyword_match(job, resume)
    job["tips"] = source_tips(job)
    history = [{"at": job.get("discovered_at"), "text": f"Found via {job.get('source') or 'unknown source'}"}]
    history += [{"at": d["created_at"], "text": f"{'CV' if d['kind'] == 'cv' else 'Cover letter'} generated"}
                for d in job["documents"] if d["kind"] in {"cv", "cover_letter"}]
    if job.get("applied_at"):
        history.append({"at": job["applied_at"], "text": "Marked as applied"})
    job["history"] = sorted([h for h in history if h["at"]], key=lambda h: h["at"], reverse=True)
    return job


def update_job(job_id, changes):
    get_job_or_404(job_id)
    fields = {}
    if "application_status" in changes:
        status = changes["application_status"]
        if status not in APPLICATION_STATUSES:
            raise HTTPException(422, f"Unknown application status “{status}”.")
        fields["application_status"] = status
        if status in {"applied", "interviewing", "offer", "rejected"} and not changes.get("applied_at"):
            current = db.one_row("SELECT applied_at FROM jobs WHERE id = ?", (job_id,))
            if not (current or {}).get("applied_at") and status != "rejected":
                fields["applied_at"] = now_iso()
    for key in ("applied_at", "follow_up_at", "notes"):
        if key in changes and changes[key] is not None:
            fields[key] = changes[key]
    if "apply_checklist" in changes and changes["apply_checklist"] is not None:
        checklist = {k: bool(v) for k, v in changes["apply_checklist"].items() if k in CHECKLIST_KEYS}
        fields["apply_checklist"] = json.dumps(checklist)
    if "status" in changes and changes["status"] in {"new", "processed", "rejected"}:
        fields["status"] = changes["status"]
    if fields:
        assignments = ", ".join(f"{key} = ?" for key in fields)
        db.execute(f"UPDATE jobs SET {assignments} WHERE id = ?", (*fields.values(), job_id))
    return job_detail(job_id)


def _groq_errors(exc):
    from tailor import GroqConfigError, describe_error

    if isinstance(exc, GroqConfigError):
        return HTTPException(400, str(exc).removeprefix("❌ ").strip() + " Add it in Settings → Integrations.")
    return HTTPException(502, f"Tailoring failed: {describe_error(exc)}. Try again in a minute.")


def preview_tailoring(job_id):
    get_job_or_404(job_id)
    from tailor import generate_tailored_content

    try:
        content = generate_tailored_content(job_id)
    except Exception as exc:
        raise _groq_errors(exc) from exc
    if not content:
        raise HTTPException(400, "The resume is missing, so there is nothing to tailor from.")
    return {"summary": content["summary"], "bullets": content["bullets"], "role_family": content["role_family"]}


def tailor_job(job_id, summary=None, bullets=None, role_family=None):
    job = get_job_or_404(job_id)
    from tailor import build_tailored_cv, generate_tailored_content

    try:
        if summary is None:
            content = generate_tailored_content(job_id)
            if not content:
                raise HTTPException(400, "The resume is missing, so there is nothing to tailor from.")
            summary, bullets, role_family = content["summary"], content["bullets"], content["role_family"]
        path = build_tailored_cv(job_id, summary, bullets or [], role_family or job.get("role_family") or None)
    except HTTPException:
        raise
    except Exception as exc:
        raise _groq_errors(exc) from exc
    if not path:
        raise HTTPException(500, "The CV could not be written. Check that the output folder is writable.")
    return {"path": path, "job": job_detail(job_id)}


def generate_cover_letter_for_job(job_id, company=None):
    job = get_job_or_404(job_id)
    from discovery import classify_target_role
    from generate_cover_letter import create_cover_letter_docx

    role_family = job.get("role_family") or classify_target_role(job.get("title") or "") or "General"
    company = (company or job.get("company") or "").strip()
    if company.startswith("Partner ("):
        company = ""
    path = create_cover_letter_docx(role_family, company=company or "the hiring team", job_title=job.get("title"))
    db.execute("UPDATE jobs SET cover_letter_path = ? WHERE id = ?", (path, job_id))
    record_document(path, "cover_letter", job_id=job_id, role_family=role_family)
    return {"path": path, "job": job_detail(job_id)}


def start_autofill(job_id, timeout=120):
    """Open a visible browser that fills the form. Returns once the fields are filled; the window stays open."""
    from api.autofill_worker import RESULT_PREFIX

    job = job_detail(job_id)
    if not job.get("url"):
        raise HTTPException(400, "This job has no posting link to open.")
    if not job["url"].lower().startswith(("http://", "https://")):
        raise HTTPException(400, "The posting link is not a web address, so it cannot be opened safely.")
    command = [sys.executable, "-m", "api.autofill_worker", job["url"], job.get("cv_path") or ""]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(command, cwd=CODE_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                               encoding="utf-8", errors="replace", env=os.environ.copy(), creationflags=creationflags)
    lines: queue.Queue[str | None] = queue.Queue()

    def reader():
        for line in process.stdout or []:
            lines.put(line)
        lines.put(None)

    threading.Thread(target=reader, daemon=True).start()
    output: list[str] = []
    deadline = datetime.now(UTC) + timedelta(seconds=timeout)
    while datetime.now(UTC) < deadline:
        try:
            line = lines.get(timeout=1)
        except queue.Empty:
            continue
        if line is None:
            break
        if line.startswith(RESULT_PREFIX):
            result = json.loads(line[len(RESULT_PREFIX):])
            result["log"] = [entry.strip() for entry in output if entry.strip()]
            return result
        output.append(line)
    tail = "".join(output[-10:]).strip()
    if "Executable doesn't exist" in tail or "playwright install" in tail:
        raise HTTPException(500, "Playwright's browser is not installed. Run `python -m playwright install chromium` once.")
    raise HTTPException(504, f"The browser did not finish filling the form in {timeout}s. {tail[-300:]}")


def delete_job(job_id, delete_files=False):
    job = job_detail(job_id)
    removed = []
    if delete_files:
        from api.routers.documents import delete_document_file

        for doc in job["documents"]:
            delete_document_file(doc)
            removed.append(doc["path"])
    db.execute_many([
        ("UPDATE documents SET job_id = NULL WHERE job_id = ?", (job_id,)),
        ("DELETE FROM jobs WHERE id = ?", (job_id,)),
    ])
    return {"deleted": job_id, "files_removed": removed}


