"""Resume API: structured and raw editing, backups, previews and imports."""
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from api.services import resume_store
from api.services.preview import sample_cv_html

router = APIRouter(prefix="/api/resume", tags=["resume"])

MAX_UPLOAD = 10 * 1024 * 1024


class ResumePut(BaseModel):
    data: dict[str, Any]
    etag: str | None = None


class RawPut(BaseModel):
    text: str
    etag: str | None = None


class PreviewRequest(BaseModel):
    data: dict[str, Any]
    role_family: str | None = None


class CommitRequest(BaseModel):
    draft: dict[str, Any]
    decisions: dict[str, str] = {}
    skills: dict[str, list[str]] = {}
    education_choice: int | None = None
    etag: str | None = None


def _invalid(exc: resume_store.ResumeInvalid):
    return HTTPException(422, {"message": exc.message, "errors": exc.errors})


@router.get("")
def get_resume():
    try:
        return resume_store.summary()
    except resume_store.ResumeInvalid as exc:
        raise HTTPException(
            422,
            {"message": "Your profile has problems. Open the YAML editor (Profile → Advanced) to fix them.", "errors": exc.errors},
        ) from exc


@router.put("")
def put_resume(body: ResumePut):
    try:
        _resume, etag, backup_id = resume_store.save(body.data, body.etag)
    except resume_store.ResumeInvalid as exc:
        raise HTTPException(422, {"message": exc.message, "errors": exc.errors}) from exc
    except resume_store.ResumeConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    return {**resume_store.summary(), "etag": etag, "backup_id": backup_id}


@router.get("/raw")
def get_raw():
    text = resume_store.read_text()
    return {"text": text, "etag": resume_store.etag_for(text)}


@router.post("/raw/validate")
def validate_raw(body: RawPut):
    try:
        resume_store.parse_raw(body.text)
        return {"valid": True, "errors": []}
    except resume_store.ResumeInvalid as exc:
        return {"valid": False, "errors": exc.errors}


@router.put("/raw")
def put_raw(body: RawPut):
    try:
        etag, backup_id = resume_store.save_raw(body.text, body.etag)
    except resume_store.ResumeInvalid as exc:
        raise _invalid(exc) from exc
    except resume_store.ResumeConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"etag": etag, "backup_id": backup_id}


@router.get("/backups")
def get_backups():
    return resume_store.list_backups()


@router.get("/backups/{backup_id}")
def get_backup(backup_id: str):
    try:
        return {"id": backup_id, "text": resume_store.read_backup(backup_id)}
    except FileNotFoundError as exc:
        raise HTTPException(404, "That backup no longer exists.") from exc


@router.post("/backups/{backup_id}/restore")
def restore_backup(backup_id: str):
    try:
        etag = resume_store.restore(backup_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, "That backup no longer exists.") from exc
    except resume_store.ResumeInvalid as exc:
        raise _invalid(exc) from exc
    return {**resume_store.summary(), "etag": etag}


@router.post("/preview")
def preview(body: PreviewRequest):
    try:
        resume = resume_store.validate(body.data)
    except resume_store.ResumeInvalid as exc:
        raise _invalid(exc) from exc
    return {"html": sample_cv_html(resume_store.to_plain(resume), body.role_family)}


async def _read_upload(file: UploadFile, max_bytes=MAX_UPLOAD):
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(413, f"The file is larger than {max_bytes // (1024 * 1024)} MB.")
    if not data:
        raise HTTPException(400, "The uploaded file is empty.")
    return data


@router.post("/import")
async def import_resume_file(file: UploadFile = File(...), enhance: bool = Form(True)):
    from api.importers.resume_file import ResumeImportError, import_resume_file

    data = await _read_upload(file)
    try:
        return import_resume_file(file.filename or "resume", data, use_ai=enhance)
    except ResumeImportError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/import/linkedin")
async def import_linkedin(file: UploadFile = File(...), enhance: bool = Form(False)):
    from api.importers.linkedin import LinkedInImportError, import_linkedin_export

    data = await _read_upload(file)
    try:
        return import_linkedin_export(data, use_ai=enhance)
    except LinkedInImportError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/import/commit")
def commit_import(body: CommitRequest):
    from api.importers.merge import apply_decisions

    current, _etag, _warnings = resume_store.load()
    try:
        merged = apply_decisions(resume_store.to_plain(current), body.draft, body.decisions, body.skills,
                                 body.education_choice)
        _resume, etag, backup_id = resume_store.save(merged, body.etag, label="import")
    except resume_store.ResumeInvalid as exc:
        raise _invalid(exc) from exc
    except resume_store.ResumeConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    return {**resume_store.summary(), "etag": etag, "backup_id": backup_id}


class ReviewRequest(BaseModel):
    source: str = "resume_file"
    draft: dict[str, Any]
    skills_pool: list[str] = []
    skill_suggestions: dict[str, str] = {}
    warnings: list[str] = []
    low_confidence: list[str] = []


@router.post("/import/review")
def review_import(body: ReviewRequest):
    """Recompute the merge view after the user edited an imported draft (nothing is saved)."""
    from api.importers.merge import build_import_result

    try:
        resume_store.validate(body.draft)
    except resume_store.ResumeInvalid as exc:
        raise _invalid(exc) from exc
    extras = {"skills_pool": body.skills_pool, "skill_categories": body.skill_suggestions}
    return build_import_result(body.source, body.draft, body.warnings, extras, low_confidence=body.low_confidence)
