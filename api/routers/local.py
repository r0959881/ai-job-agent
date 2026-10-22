"""The local account's project files, for runs on your own PC (`start.ps1`).

The web app keeps jobs in the browser and files in a folder the user picks. On
your own PC the local account instead uses what the project already has: the
jobs in jobs.db (from the command line and the old UI) and the documents in
output/. New CVs and reports are written to output/ as before. None of this
exists on a server: every route answers 404 unless local mode is on.
"""
import json
import os
import queue
import sqlite3
import subprocess
import sys
import threading
import time
from contextlib import closing
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from api import server_config
from api.auth import uses_project_files
from config import CODE_ROOT, DB_PATH, OUTPUT_DIR, RUNS_DIR, relative_to_project

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
    stem = lower.rsplit(".", 1)[0]
    if "_cover_letter_" in lower or stem.endswith("_cl"):
        return "cover_letter"
    if ("_cv_" in lower or stem.endswith("_cv")) and lower.endswith((".docx", ".pdf")):
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


class AutofillBody(BaseModel):
    url: str
    cv_path: str = ""
    cover_letter_path: str = ""


def _output_file(path):
    """'output/x.pdf' as an existing file inside output/, or "" (never a path outside it)."""
    if not path:
        return ""
    name = path.removeprefix("output/")
    try:
        file = _file(name)
    except HTTPException:
        return ""
    return f"output/{file.name}" if file.exists() else ""


@router.post("/autofill")
def autofill(body: AutofillBody, request: Request, timeout: int = 120):
    """Open a visible browser on this PC that goes to the posting, clicks Apply and fills the form.

    It attaches the CV and cover letter and keeps filling new fields until the window is closed.
    Nothing is ever submitted: the user checks every field and submits.
    """
    _require_local(request)
    if not body.url.lower().startswith(("http://", "https://")):
        raise HTTPException(400, "The posting link is not a web address, so it cannot be opened safely.")
    from api.autofill_worker import RESULT_PREFIX

    command = [sys.executable, "-m", "api.autofill_worker", body.url, _output_file(body.cv_path),
               _output_file(body.cover_letter_path)]
    process = subprocess.Popen(command, cwd=CODE_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                               encoding="utf-8", errors="replace", env=os.environ.copy(),
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    lines: queue.Queue[str | None] = queue.Queue()

    def reader():
        for line in process.stdout or []:
            lines.put(line)
        lines.put(None)

    threading.Thread(target=reader, daemon=True).start()
    output: list[str] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
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
    if "No module named 'playwright'" in tail:
        raise HTTPException(500, "Playwright is not installed. Run `pip install -r requirements-local.txt`.")
    raise HTTPException(504, f"The browser did not finish filling the form in {timeout}s. {tail[-300:]}")
