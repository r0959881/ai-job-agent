"""Jobs grid, job detail and the Apply workspace actions."""
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from api.services import jobs

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
def list_jobs(
    q: str | None = None,
    status: list[str] = Query(default_factory=list),
    application_status: list[str] = Query(default_factory=list),
    role_family: list[str] = Query(default_factory=list),
    source: list[str] = Query(default_factory=list),
    date_from: str | None = None,
    date_to: str | None = None,
    has_cv: bool | None = None,
    quick: Literal["ready", "applied_week", "follow_up"] | None = None,
    sort: str = "posted",
    order: Literal["asc", "desc"] = "desc",
    page: int = 1,
    page_size: int = 50,
):
    return jobs.list_jobs(locals())


class JobPatch(BaseModel):
    application_status: str | None = None
    applied_at: str | None = None
    follow_up_at: str | None = None
    notes: str | None = None
    apply_checklist: dict[str, bool] | None = None
    status: str | None = None


@router.get("/{job_id}")
def get_job(job_id: str):
    return jobs.job_detail(job_id)


@router.patch("/{job_id}")
def patch_job(job_id: str, body: JobPatch):
    return jobs.update_job(job_id, body.model_dump(exclude_unset=True))


class TailorBody(BaseModel):
    summary: str | None = None
    bullets: list[str] | None = None
    role_family: str | None = None


@router.post("/{job_id}/tailor/preview")
def tailor_preview(job_id: str):
    return jobs.preview_tailoring(job_id)


@router.post("/{job_id}/tailor")
def tailor(job_id: str, body: TailorBody | None = None):
    body = body or TailorBody()
    return jobs.tailor_job(job_id, body.summary, body.bullets, body.role_family)


class CoverLetterBody(BaseModel):
    company: str | None = None


@router.post("/{job_id}/cover-letter")
def cover_letter(job_id: str, body: CoverLetterBody | None = None):
    return jobs.generate_cover_letter_for_job(job_id, (body or CoverLetterBody()).company)


@router.post("/{job_id}/autofill")
def autofill(job_id: str):
    return jobs.start_autofill(job_id)


@router.delete("/{job_id}")
def delete_job(job_id: str, delete_files: bool = False):
    return jobs.delete_job(job_id, delete_files)


class BulkBody(BaseModel):
    ids: list[str]
    action: Literal["skip", "regenerate", "delete"]
    delete_files: bool = False


@router.post("/bulk")
def bulk(body: BulkBody):
    done, failed = [], []
    for job_id in body.ids[:500]:
        try:
            if body.action == "skip":
                jobs.update_job(job_id, {"application_status": "skipped"})
            elif body.action == "regenerate":
                jobs.tailor_job(job_id)
            else:
                jobs.delete_job(job_id, body.delete_files)
            done.append(job_id)
        except Exception as exc:  # Report per-job failures instead of stopping the batch.
            failed.append({"id": job_id, "reason": getattr(exc, "detail", None) or str(exc)})
    return {"done": done, "failed": failed}
