"""Data tools: open the output folder, export everything, reset the jobs database."""
import os
import tempfile
import zipfile
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from api import db
from config import DB_PATH, OUTPUT_DIR, RESUME_PATH, SETTINGS_PATH, long_path

router = APIRouter(prefix="/api/data", tags=["data"])


@router.post("/open-output")
def open_output():
    from api.routers.documents import _open_path

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _open_path(OUTPUT_DIR)
    return {"opened": str(OUTPUT_DIR)}


@router.get("/export")
def export_all():
    """Zip of the resume, settings, jobs database and generated documents. Secrets are never included."""
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    handle = tempfile.NamedTemporaryFile(prefix="ai_job_agent_export_", suffix=".zip", delete=False)
    handle.close()
    with zipfile.ZipFile(handle.name, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in (RESUME_PATH, SETTINGS_PATH, DB_PATH):
            if path.exists():
                archive.write(path, path.name)
        if OUTPUT_DIR.exists():
            for file in OUTPUT_DIR.rglob("*"):
                if file.is_file() and not file.name.startswith("~$"):
                    archive.write(long_path(file), f"output/{file.relative_to(OUTPUT_DIR).as_posix()}")
    return FileResponse(handle.name, filename=f"ai_job_agent_export_{stamp}.zip", media_type="application/zip",
                        background=BackgroundTask(os.remove, handle.name))


class ResetBody(BaseModel):
    confirm: str


@router.post("/reset-jobs")
def reset_jobs(body: ResetBody):
    if body.confirm != "RESET":
        raise HTTPException(400, "Type RESET to confirm.")
    count = db.one_row("SELECT COUNT(*) AS n FROM jobs")["n"]
    db.execute_many([
        ("UPDATE documents SET job_id = NULL WHERE job_id IS NOT NULL", ()),
        ("DELETE FROM jobs", ()),
    ])
    return {"deleted": count}
