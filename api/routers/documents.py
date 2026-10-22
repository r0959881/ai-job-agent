"""Documents for the web app: tailored CVs, cover letters, the Excel report and previews.

Every file is built in memory from the user's resume and returned to the
browser, which saves it in the folder the user picked. Nothing is written on
the server, so generated documents never take up space there.
"""
import base64
import html
import io
import re
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from api.services.preview import sanitise
from agent_log import log
from config import company_in_title, load_resume_file

router = APIRouter(prefix="/api", tags=["documents"])

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF = "application/pdf"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_PREVIEW = 10 * 1024 * 1024


class JobIn(BaseModel):
    id: str = ""
    title: str
    company: str = ""
    location: str = ""
    url: str = ""
    source: str = ""
    description: str = ""
    role_family: str = ""


class TailorBody(BaseModel):
    job: JobIn
    summary: str | None = None
    bullets: list[str] | None = None
    role_family: str | None = None
    # The catch phrase under the name and the skills to lead with (both optional).
    tagline: str | None = None
    skills: list[str] | None = None


class CoverLetterBody(BaseModel):
    job: JobIn
    company: str | None = None


class ReportBody(BaseModel):
    jobs: list[dict[str, Any]]
    excluded: list[dict[str, Any]] = []
    name: str = ""


def file_payload(name, mime, data: bytes):
    return {"name": name, "mime": mime, "size": len(data), "data": base64.b64encode(data).decode("ascii")}


def _resume():
    resume = load_resume_file()
    if not resume or not any(resume.get(key) for key in ("experience", "projects", "core_skills")):
        raise HTTPException(400, "Your profile is empty. Fill it in under Profile (or import a CV) first.")
    return resume


def _groq_error(exc):
    from tailor import GroqConfigError, describe_error

    if isinstance(exc, GroqConfigError):
        return HTTPException(400, str(exc).removeprefix("❌ ").strip())
    return HTTPException(502, f"Tailoring failed: {describe_error(exc)}. Try again in a minute.")


def _role_family(job: JobIn):
    from discovery import classify_target_role

    return job.role_family or classify_target_role(job.title, job.description) or ""


@router.post("/tailor/preview")
def tailor_preview(body: TailorBody):
    """The tailored summary and bullets, for the user to review before the CV is written."""
    from tailor import tailored_content_for

    resume = _resume()
    job = body.job.model_dump() | {"role_family": _role_family(body.job)}
    try:
        content = tailored_content_for(job, resume=resume)
    except Exception as exc:
        raise _groq_error(exc) from exc
    return {key: content.get(key) for key in ("tagline", "summary", "skills", "bullets", "role_family")}


@router.post("/tailor")
def tailor(body: TailorBody):
    """Write the tailored CV (PDF). Without summary and bullets they are generated first."""
    from generate_doc import create_tailored_cv, cv_file_stem
    from tailor import tailored_content_for

    resume = _resume()
    role_family = body.role_family if body.role_family is not None else _role_family(body.job)
    summary, bullets, tagline, skills = body.summary, body.bullets, body.tagline or "", body.skills
    if summary is None:
        try:
            content = tailored_content_for(body.job.model_dump() | {"role_family": role_family}, resume=resume)
        except Exception as exc:
            raise _groq_error(exc) from exc
        summary, bullets, role_family = content["summary"], content["bullets"], content["role_family"]
        tagline, skills = content.get("tagline") or "", content.get("skills")
    buffer = io.BytesIO()
    create_tailored_cv(body.job.company, body.job.title, summary, bullets or [], role_family or None,
                       data=resume, output_path=buffer, tagline=tagline, skills=skills, job_text=body.job.description)
    name = cv_file_stem((resume.get("personal_info") or {}).get("full_name"), body.job.company, body.job.title)
    return {"tagline": tagline, "summary": summary, "bullets": bullets or [], "skills": skills or [],
            "role_family": role_family or "", "file": file_payload(f"{name}.pdf", PDF, buffer.getvalue())}


@router.post("/cover-letter")
def cover_letter(body: CoverLetterBody):
    from generate_cover_letter import cover_letter_stem, create_cover_letter_docx, written_paragraphs

    resume = _resume()
    role_family = _role_family(body.job) or "General"
    company = (body.company or body.job.company or "").strip()
    if company.startswith("Partner ("):
        company = company_in_title(body.job.title)
    try:  # a letter written for this job; the role family's letter when Groq is unavailable
        paragraphs = written_paragraphs(body.job.model_dump() | {"company": company}, resume)
    except Exception as exc:
        log(f"⚠️ Cover letter written from the role template: {exc}", level="warning")
        paragraphs = None
    buffer = io.BytesIO()
    create_cover_letter_docx(role_family, company=company or "the hiring team", job_title=body.job.title,
                             data=resume, output_path=buffer, location=body.job.location, paragraphs=paragraphs)
    name = cover_letter_stem((resume.get("personal_info") or {}).get("full_name"), role_family, company,
                             body.job.title)
    return {"role_family": role_family, "tailored": paragraphs is not None,
            "file": file_payload(f"{name}.docx", DOCX, buffer.getvalue())}


@router.post("/report")
def report(body: ReportBody):
    """The Excel report of a run. Each job's cv_path is the CV's path relative to the report."""
    from datetime import UTC, datetime

    from report import export_jobs_to_excel

    if len(body.jobs) + len(body.excluded) > 5000:
        raise HTTPException(413, "A report can hold at most 5000 jobs.")
    buffer = io.BytesIO()
    export_jobs_to_excel([dict(job) for job in body.jobs], buffer, [dict(job) for job in body.excluded],
                         relative_cv_links=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    name = re.sub(r"[^\w.-]", "_", body.name) if body.name else f"job_report_{stamp}.xlsx"
    return {"file": file_payload(name if name.endswith(".xlsx") else f"{name}.xlsx", XLSX, buffer.getvalue())}


@router.post("/documents/preview")
async def preview(file: UploadFile = File(...)):
    """Render a Word or text file from the user's folder as HTML (the file is not kept)."""
    import mammoth

    data = await file.read(MAX_PREVIEW + 1)
    if len(data) > MAX_PREVIEW:
        raise HTTPException(413, "The file is too large to preview.")
    name = (file.filename or "").lower()
    if name.endswith(".docx"):
        try:
            result = mammoth.convert_to_html(io.BytesIO(data))
        except Exception as exc:
            raise HTTPException(415, "This Word file could not be read.") from exc
        return {"html": sanitise(result.value)}
    if name.endswith(".txt"):
        return {"html": f"<pre>{html.escape(data.decode('utf-8', errors='replace')[:200_000])}</pre>"}
    raise HTTPException(415, "Only Word documents and text files can be previewed. Open this file instead.")


@router.post("/jobs/insights")
def insights(job: JobIn):
    """Resume keywords found in the posting, role keywords it does not mention, and tips for its source."""
    from api.services.job_insights import keyword_match, source_tips

    data = job.model_dump()
    data["role_family"] = _role_family(job)
    matched, missing = keyword_match(data, load_resume_file() or {})
    return {"matched_keywords": matched, "missing_keywords": missing, "tips": source_tips(data),
            "role_family": data["role_family"]}
