"""The local account's project files, for runs on your own PC (`start.ps1`).

The web app keeps jobs in the browser and files in a folder the user picks. On
your own PC the local account instead uses what the project already has: the
jobs in jobs.db (from the command line and the old UI) and the documents in
output/. New CVs and reports are written to output/ as before. None of this
exists on a server: every route answers 404 unless local mode is on.
"""
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from api import server_config
from api.auth import uses_project_files
from config import DB_PATH, OUTPUT_DIR, RUNS_DIR, relative_to_project

router = APIRouter(prefix="/api/local", tags=["local"])

DOCUMENT_SUFFIXES = {".docx", ".xlsx", ".txt", ".pdf"}
DATA_FILE = "ai-job-agent-data.json"
MAX_FILE = 20 * 1024 * 1024


def _require_local(request: Request):
    if not uses_project_files(request.session):
        raise HTTPException(404, "Project files are only available to the local account on your own PC.")


def _file(name: str):
    """A file directly inside output/ (no sub-folders, no way out of it)."""
    if not name or name != name.strip() or "/" in name or "\\" in name or name in {".", ".."}:
        raise HTTPException(400, "Use a plain file name.")
    path = OUTPUT_DIR / name
    if path.resolve().parent != OUTPUT_DIR.resolve():
        raise HTTPException(400, "Use a plain file name.")
    return path


def classify(name):
    lower = name.lower()
    if lower.endswith(".xlsx") and lower.startswith("job_report"):
        return "report"
    if "_cover_letter_" in lower:
        return "cover_letter"
    if "_cv_" in lower and lower.endswith(".docx"):
        return "cv"
    return "other"


def _stamp(path):
    return datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()


@router.get("/legacy")
def legacy(request: Request):
    """Jobs from jobs.db and the documents in output/, in the shapes the web app stores."""
    _require_local(request)
    jobs, documents, runs, seen = [], [], [], set()
    if DB_PATH.exists():
        with closing(sqlite3.connect(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            for row in conn.execute("SELECT * FROM jobs") if "jobs" in tables else []:
                job = dict(row)
                job.pop("source_data", None)
                try:
                    job["apply_checklist"] = json.loads(job.get("apply_checklist") or "{}")
                except ValueError:
                    job["apply_checklist"] = {}
                for key, value in list(job.items()):
                    if value is None and key not in {"salary_min", "salary_max"}:
                        job[key] = ""
                job["application_status"] = job.get("application_status") or "not_applied"
                jobs.append(job)
            for row in conn.execute("SELECT * FROM runs ORDER BY id") if "runs" in tables else []:
                runs.append(_run(dict(row)))
            for row in conn.execute("SELECT * FROM documents") if "documents" in tables else []:
                path = relative_to_project(OUTPUT_DIR.parent / row["path"]) if row["path"] else ""
                file = OUTPUT_DIR.parent / path
                if not path.startswith("output/") or "/" in path[len("output/"):] or not file.exists():
                    continue
                seen.add(path)
                documents.append({"job_id": row["job_id"], "kind": row["kind"] or classify(file.name),
                                  "role_family": row["role_family"] or "", "path": path, "name": file.name,
                                  "created_at": row["created_at"] or _stamp(file), "size": file.stat().st_size})
    cv_owner = {job[key]: job["id"] for job in jobs for key in ("cv_path", "cover_letter_path") if job.get(key)}
    if OUTPUT_DIR.exists():
        for file in sorted(OUTPUT_DIR.iterdir()):
            path = f"output/{file.name}"
            if (path in seen or not file.is_file() or file.suffix.lower() not in DOCUMENT_SUFFIXES
                    or file.name.startswith(("~$", "."))):
                continue
            documents.append({"job_id": cv_owner.get(path), "kind": classify(file.name), "role_family": "",
                              "path": path, "name": file.name, "created_at": _stamp(file),
                              "size": file.stat().st_size})
    return {"jobs": jobs, "documents": documents, "runs": runs}


def _run(row):
    """A run recorded by the old UI, with its event log, in the web app's run shape."""
    events = []
    log = RUNS_DIR / f"run_{row['id']}.events.jsonl"
    if log.exists():
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
    for key in ("options", "summary"):
        try:
            row[key] = json.loads(row.get(key) or "{}")
        except ValueError:
            row[key] = {}
    row.pop("id", None)
    return {**{key: value if value is not None else "" for key, value in row.items()}, "events": events}


@router.get("/files")
def list_files(request: Request):
    _require_local(request)
    if not OUTPUT_DIR.exists():
        return {"items": []}
    return {"items": [{"name": f.name, "path": f"output/{f.name}", "size": f.stat().st_size,
                       "modified": _stamp(f), "kind": classify(f.name)}
                      for f in sorted(OUTPUT_DIR.iterdir())
                      if f.is_file() and f.suffix.lower() in DOCUMENT_SUFFIXES and not f.name.startswith(("~$", "."))]}


@router.get("/files/{name}")
def read_file(name: str, request: Request):
    _require_local(request)
    path = _file(name)
    if not path.exists():
        raise HTTPException(404, f"{name} is no longer in the output folder.")
    return FileResponse(path, filename=path.name)


@router.put("/files/{name}")
async def write_file(name: str, request: Request):
    _require_local(request)
    path = _file(name)
    data = await request.body()
    if len(data) > MAX_FILE:
        raise HTTPException(413, "The file is too large.")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_bytes(data)
    try:
        temp.replace(path)
    except PermissionError as exc:
        temp.unlink(missing_ok=True)
        raise HTTPException(409, f"{name} is open in another program (Word?). Close it and try again.") from exc
    return {"path": f"output/{path.name}", "size": len(data)}


@router.delete("/files/{name}")
def delete_file(name: str, request: Request):
    _require_local(request)
    path = _file(name)
    try:
        path.unlink(missing_ok=True)
    except PermissionError as exc:
        raise HTTPException(409, f"{name} is open in another program. Close it and try again.") from exc
    return {"deleted": f"output/{path.name}"}


@router.get("/status")
def status(request: Request):
    _require_local(request)
    return {"output": str(OUTPUT_DIR), "data_file": DATA_FILE, "local": server_config.local_mode()}
