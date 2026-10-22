import os
import re
import yaml
from dotenv import load_dotenv
from groq import Groq
import user_scope
from agent_log import log
from config import DB_PATH, ENV_PATH, load_resume_file
from database import connect, record_document
from generate_doc import create_tailored_cv
from discovery import classify_target_role, get_target_roles

# 1. Load environment variables (.env file)
load_dotenv(ENV_PATH)

MODEL = "openai/gpt-oss-120b"


class GroqConfigError(Exception):
    """GROQ_API_KEY is missing or invalid."""


def check_groq_key():
    """Return the key, or raise GroqConfigError with the CLI's friendly message."""
    groq_api_key = user_scope.secret("GROQ_API_KEY")
    where = "in Settings → Integrations" if user_scope.current() else "as GROQ_API_KEY in .env"
    if not groq_api_key:
        raise GroqConfigError(f"❌ No Groq API key is set. Add your free Groq key {where}.")
    if not groq_api_key.startswith("gsk_"):
        raise GroqConfigError(f"❌ The Groq API key is invalid (it should start with gsk_). Set a new key {where}.")
    return groq_api_key


def get_client():
    """2. Create the Groq client on first use instead of at import time."""
    return Groq(api_key=check_groq_key())


def load_master_resume():
    resume = load_resume_file()
    if resume is None:
        log("❌ Error: resume_data.yaml not found!", level="error")
    return resume


def _join_choices(names):
    names = list(names)
    if len(names) <= 1:
        return "".join(names)
    return f"{', '.join(names[:-1])}, or {names[-1]}"


def describe_error(error):
    """Short, specific reason for the run summary (e.g. 'Groq timed out')."""
    name = type(error).__name__
    text = str(error).lower()
    if "timeout" in name.lower() or "timed out" in text:
        return "Groq timed out"
    if "ratelimit" in name.lower() or "rate limit" in text or "429" in text:
        return "Groq rate limit reached"
    if "authentication" in name.lower() or "401" in text or "invalid api key" in text:
        return "Groq rejected the API key"
    if "connection" in name.lower():
        return "Could not reach Groq"
    return f"{name}: {error}"


def get_job(job_id):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT title, company, location, url FROM jobs WHERE id = ?", (job_id,))
    job = cursor.fetchone()
    conn.close()
    return job


def get_job_description(job_id):
    conn = connect()
    row = conn.execute("SELECT description FROM jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    return (row[0] if row else "") or ""


def generate_tailored_content(job_id, client=None):
    """Ask Groq for the summary and bullets. Raises on API errors.

    Returns {"summary", "bullets", "role_family", "raw"} or None when the job or resume is missing.
    """
    job = get_job(job_id)
    if not job:
        log("❌ Job not found in database!", level="error")
        return None
    title, company, _location, _url = job
    return tailored_content_for({"title": title, "company": company, "description": get_job_description(job_id)},
                                client=client)


JOB_TEXT_LIMIT = 4500


def _experience_list(resume):
    lines = []
    for number, entry in enumerate(resume.get("experience") or [], start=1):
        if isinstance(entry, dict):
            lines.append(f"[{number}] {entry.get('role', '')} at {entry.get('company', '')} ({entry.get('dates', '')})")
    return "\n".join(lines) or "(no experience entries)"


def parse_tailored(text):
    """TAGLINE / SUMMARY / SKILLS / BULLETS from the model's answer (older SUMMARY+BULLETS answers too)."""
    content = {"tagline": "", "summary": "", "skills": [], "bullets": []}
    section = None
    for raw_line in (text or "").strip().splitlines():
        line = raw_line.strip()
        upper = line.upper()
        for key in ("TAGLINE", "SUMMARY", "SKILLS"):
            if upper.startswith(f"{key}:"):
                value = line[len(key) + 1:].strip()
                if key == "SKILLS":
                    content["skills"] = [part.strip(" .*") for part in value.split(",") if part.strip(" .*")]
                else:
                    content[key.lower()] = value.strip("\"")
                section = key
                break
        else:
            if upper.startswith("BULLETS"):
                section = "BULLETS"
            elif line.startswith(("- ", "* ", "• ")):
                content["bullets"].append(line[2:].strip())
            elif line and section == "SUMMARY" and not content["bullets"]:
                content["summary"] = f"{content['summary']} {line}".strip()
    if not content["summary"]:
        content["summary"] = (text or "").strip()
    return content


def tailored_content_for(job, client=None, resume=None):
    """Ask Groq for the catch phrase, summary, skills and bullets for a job given as a dict.

    The job may carry title, company, role_family and description. Raises on API errors.
    Returns {"tagline", "summary", "skills", "bullets", "role_family", "raw"}, or None without a resume.
    """
    title, company = job.get("title") or "", job.get("company") or ""
    description = (job.get("description") or "").strip()[:JOB_TEXT_LIMIT]
    log(f"🤖 Tailoring CV for: {title} at {company}...")
    role_family = job.get("role_family") or classify_target_role(title, description)

    resume = resume if resume is not None else load_master_resume()
    if not resume:
        return None

    role_profile = resume.get("role_profiles", {}).get(role_family or "", {})
    role_names = list(get_target_roles())
    company_hint = "" if company.startswith("Partner (") or company in {"", "Unknown"} else company

    prompt = f"""
    You are an expert recruiter and ATS optimisation assistant. Tailor a TWO-PAGE CV to this job.

    Job title: {title}
    Company: {company_hint or "(unknown: do not name a company)"}
    Job posting:
    \"\"\"
    {description or "(no description available: rely on the title)"}
    \"\"\"

    Target role family: {role_family or 'Choose the closest match'} (options: {_join_choices(role_names)})
    Role focus: {role_profile.get('focus', 'Match the job requirements to the master resume facts.')}
    Priority keywords: {', '.join(role_profile.get('keywords', []))}

    Experience entries (refer to them by number):
    {_experience_list(resume)}

    Master resume (the only source of facts):
    {yaml.dump(resume, default_flow_style=False, allow_unicode=True)}

    Write, in the language of the job posting:
    1. TAGLINE: one catch phrase of at most 14 words that shows motivation for THIS job, naming the role
       {"and " + company_hint if company_hint else ""} (e.g. "Junior Data Engineer ready to scale Acme's data platform").
    2. SUMMARY: 2 sentences, at most 55 words, connecting my real experience to what the posting asks for.
    3. SKILLS: 8 to 12 skills from my resume, most relevant to the posting first, comma separated.
    4. BULLETS: 4 to 6 achievement bullets rephrased from my experience, the strongest matches first.
       Start each with the number of the experience entry it comes from, like [1]. At most 28 words each.
       Wrap the 1-3 terms in each bullet that matter most for this job in **double asterisks**.

    CRITICAL RULES:
    - Do not invent, embellish or assume any experience, skill, number, company, tool or degree that is not in my
      master resume. Leave something out rather than make it up.
    - Copy every number exactly as it is written in the resume (80%, 50+, 12-week...) and keep it attached to the
      same achievement it belongs to there. Never move a number to a different achievement.
    - Never state a number of years of experience unless the resume states it.

    Answer EXACTLY in this format and nothing else:
    TAGLINE: <catch phrase>
    SUMMARY: <2 sentences>
    SKILLS: <skill>, <skill>, ...
    BULLETS:
    - [1] <bullet>
    - [2] <bullet>
    """

    client = client or get_client()
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )

    tailored_text = response.choices[0].message.content
    log("\n--- Tailored AI Output ---\n")
    log(tailored_text)
    content = parse_tailored(tailored_text)
    content["bullets"] = keep_verifiable(content["bullets"], resume)
    content["summary"] = drop_unverifiable_sentences(content["summary"], resume) or (
        (resume.get("personal_info") or {}).get("headline") or "")
    content["tagline"] = drop_unverifiable_sentences(content["tagline"], resume)
    return {**content, "role_family": role_family or "", "raw": tailored_text}


_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _known_numbers(resume):
    return set(_NUMBER.findall(yaml.dump(resume, allow_unicode=True)))


def drop_unverifiable_sentences(text, resume):
    """Remove sentences that state a number the resume does not contain ("1.5 years of experience")."""
    known = _known_numbers(resume)
    sentences = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    kept = [s for s in sentences if all(number in known for number in _NUMBER.findall(s))]
    if len(kept) < len(sentences):
        log(f"⚠️ Left out a sentence with a number that is not in the resume: {' '.join(set(sentences) - set(kept))}",
            level="warning")
    return " ".join(kept).strip()


def keep_verifiable(bullets, resume):
    """Drop bullets that state a number the resume does not contain (the CV then uses the original bullets)."""
    known = _known_numbers(resume)
    kept = []
    for bullet in bullets:
        unknown = [number for number in _NUMBER.findall(re.sub(r"^\s*\[\d+\]", "", bullet)) if number not in known]
        if unknown:
            log(f"⚠️ Left out a tailored bullet with a number that is not in the resume ({', '.join(unknown)}): {bullet}",
                level="warning")
            continue
        kept.append(bullet)
    return kept


def build_tailored_cv(job_id, summary, bullets, role_family=None, run_id=None, tagline="", skills=None):
    """Write the DOCX from (possibly user-edited) content and link it to the job."""
    job = get_job(job_id)
    if not job:
        log("❌ Job not found in database!", level="error")
        return None
    title, company, _location, _url = job
    role_family = role_family if role_family is not None else classify_target_role(title)
    docx_path = create_tailored_cv(company, title, summary, bullets, role_family, tagline=tagline,
                                        skills=skills, job_text=get_job_description(job_id))
    if not docx_path:
        return None

    conn = connect()
    conn.execute(
        "UPDATE jobs SET status = 'processed', cv_path = ?, role_family = ? WHERE id = ?",
        (docx_path, role_family or "", job_id),
    )
    conn.commit()
    conn.close()
    record_document(docx_path, "cv", job_id=job_id, role_family=role_family or "", run_id=run_id)
    return docx_path


def tailor_cv_for_job(job_id, client=None, run_id=None, raise_errors=False):
    try:
        content = generate_tailored_content(job_id, client=client)
        if not content:
            return None
        return build_tailored_cv(job_id, content["summary"], content["bullets"], content["role_family"], run_id=run_id,
                                 tagline=content.get("tagline", ""), skills=content.get("skills"))

    except Exception as e:
        log(f"❌ Error communicating with Groq API: {e}", level="error", data={"reason": describe_error(e)})
        if raise_errors:
            raise
        return None

if __name__ == "__main__":
    try:
        check_groq_key()
    except GroqConfigError as error:
        raise SystemExit(str(error))
    if DB_PATH.exists():
        conn = connect()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM jobs WHERE status = 'new' LIMIT 1")
        next_job = cursor.fetchone()
        conn.close()

        if next_job:
            tailor_cv_for_job(next_job[0])
        else:
            print("⚠️ No new unprocessed jobs found in database!")
    else:
        print("⚠️ jobs.db does not exist yet. Run 'python database.py' and 'python discovery.py' first!")
