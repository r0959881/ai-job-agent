"""Generated documents: list, preview, download, open locally, regenerate and delete."""
import os
import subprocess
import sys

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from api import db
from api.paths import safe_output_path
from api.services.documents import backfill_documents, document_row
from api.services.preview import docx_to_html, text_preview
from config import OUTPUT_DIR, long_path

router = APIRouter(prefix="/api", tags=["documents"])

MEDIA_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".txt": "text/plain; charset=utf-8",
    ".pdf": "application/pdf",
}

BASE_QUERY = """SELECT d.*, j.title AS job_title, j.company AS job_company
FROM documents d LEFT JOIN jobs j ON j.id = d.job_id"""


def _get(document_id):
    row = db.one_row(f"{BASE_QUERY} WHERE d.id = ?", (document_id,))
    if not row:
        raise HTTPException(404, "That document no longer exists.")
    return row


@router.get("/documents")
def list_documents(kind: str | None = None, role_family: str | None = None, q: str | None = None,
                   job_id: str | None = None, orphans: bool = False, rescan: bool = False):
    if rescan:
        backfill_documents()
    clauses, params = [], []
    if kind:
        clauses.append("d.kind = ?")
        params.append(kind)
    if role_family:
        clauses.append("d.role_family = ?")
        params.append(role_family)
    if job_id:
        clauses.append("d.job_id = ?")
        params.append(job_id)
    if orphans:
        clauses.append("(d.job_id IS NULL OR j.id IS NULL) AND d.kind != 'report'")
    if q:
        clauses.append("(d.path LIKE ? OR j.title LIKE ? OR j.company LIKE ?)")
        params += [f"%{q}%"] * 3
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = db.all_rows(f"{BASE_QUERY}{where} ORDER BY d.created_at DESC, d.id DESC", tuple(params))
    return {"items": [document_row(row) for row in rows]}


@router.post("/documents/rescan")
def rescan():
    return backfill_documents()


@router.get("/documents/{document_id}/download")
def download(document_id: int):
    row = _get(document_id)
    path = safe_output_path(row["path"])
    if not path.exists():
        raise HTTPException(404, "The file was deleted from the output folder.")
    return FileResponse(long_path(path), filename=path.name,
                        media_type=MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream"))


@router.get("/documents/{document_id}/preview")
def preview(document_id: int):
    row = _get(document_id)
    path = safe_output_path(row["path"])
    if not path.exists():
        raise HTTPException(404, "The file was deleted from the output folder.")
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return {"html": docx_to_html(path), "kind": row["kind"]}
    if suffix == ".txt":
        return {"html": text_preview(path), "kind": row["kind"]}
    raise HTTPException(415, "Only Word documents and text files can be previewed. Download this file instead.")


@router.post("/documents/{document_id}/open")
def open_locally(document_id: int):
    """Open the file in its desktop app (Word/Excel). Browsers block file:// links from web pages."""
    row = _get(document_id)
    path = safe_output_path(row["path"])
    if not path.exists():
        raise HTTPException(404, "The file was deleted from the output folder.")
    _open_path(path)
    return {"opened": path.name}


def _open_path(path):
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def delete_document_file(row):
    path = safe_output_path(row["path"])
    try:
        os.remove(long_path(path))
    except FileNotFoundError:
        pass
    except PermissionError as exc:
        raise HTTPException(409, f"{path.name} is open in another program. Close it and try again.") from exc
    statements = [("DELETE FROM documents WHERE id = ?", (row["id"],))]
    if row.get("job_id"):
        column = "cv_path" if row["kind"] == "cv" else "cover_letter_path" if row["kind"] == "cover_letter" else None
        if column:
            statements.append((f"UPDATE jobs SET {column} = '' WHERE id = ? AND {column} = ?", (row["job_id"], row["path"])))
            if column == "cv_path":
                statements.append(("UPDATE jobs SET status = 'new' WHERE id = ? AND status = 'processed' AND cv_path = ''",
                                   (row["job_id"],)))
    db.execute_many(statements)


@router.delete("/documents/{document_id}")
def delete_document(document_id: int):
    row = _get(document_id)
    delete_document_file(row)
    return {"deleted": row["path"]}


class BulkDelete(BaseModel):
    ids: list[int]


@router.post("/documents/bulk-delete")
def bulk_delete(body: BulkDelete):
    deleted, failed = [], []
    for document_id in body.ids:
        row = db.one_row(f"{BASE_QUERY} WHERE d.id = ?", (document_id,))
        if not row:
            continue
        try:
            delete_document_file(row)
            deleted.append(document_id)
        except HTTPException as exc:
            failed.append({"id": document_id, "reason": exc.detail})
    return {"deleted": deleted, "failed": failed}


@router.post("/documents/{document_id}/regenerate")
def regenerate(document_id: int):
    row = _get(document_id)
    if not row.get("job_id"):
        if row["kind"] == "cover_letter" and row.get("role_family"):
            from generate_cover_letter import create_cover_letter_docx

            path = create_cover_letter_docx(row["role_family"])
            backfill_documents()
            return {"path": path}
        raise HTTPException(400, "This file is not linked to a job, so there is nothing to regenerate it from.")
    from api.services.jobs import generate_cover_letter_for_job, tailor_job

    if row["kind"] == "cv":
        return tailor_job(row["job_id"])
    if row["kind"] == "cover_letter":
        return generate_cover_letter_for_job(row["job_id"])
    raise HTTPException(400, "Only CVs and cover letters can be regenerated.")


@router.get("/reports/latest")
def latest_report():
    row = db.one_row("SELECT * FROM documents WHERE kind = 'report' ORDER BY created_at DESC, id DESC LIMIT 1")
    path = safe_output_path(row["path"]) if row else None
    if not path or not path.exists():
        reports = sorted(OUTPUT_DIR.glob("job_report_*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not reports:
            raise HTTPException(404, "No Excel report yet. Run the agent to create one.")
        path = reports[0]
    return FileResponse(long_path(path), filename=path.name, media_type=MEDIA_TYPES[".xlsx"])
