import os
import yaml
from dotenv import load_dotenv
from groq import Groq
from agent_log import log
from config import DB_PATH, ENV_PATH, load_resume_file
from database import connect, record_document
from generate_doc import create_tailored_cv_docx
from discovery import classify_target_role, get_target_roles

# 1. Load environment variables (.env file)
load_dotenv(ENV_PATH)

MODEL = "openai/gpt-oss-120b"


class GroqConfigError(Exception):
    """GROQ_API_KEY is missing or invalid."""


def check_groq_key():
    """Return the key, or raise GroqConfigError with the CLI's friendly message."""
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        raise GroqConfigError(
            "❌ GROQ_API_KEY is not configured. "
            "Copy .env.example to .env and add your Groq API key."
        )
    if not groq_api_key.startswith("gsk_"):
        raise GroqConfigError(
            "❌ GROQ_API_KEY is invalid or still a placeholder. "
            "Create a new Groq key and set it as GROQ_API_KEY in .env."
        )
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


def generate_tailored_content(job_id, client=None):
    """Ask Groq for the summary and bullets. Raises on API errors.

    Returns {"summary", "bullets", "role_family", "raw"} or None when the job or resume is missing.
    """
    job = get_job(job_id)
    if not job:
        log("❌ Job not found in database!", level="error")
        return None

    title, company, location, url = job
    log(f"🤖 Tailoring CV for: {title} at {company}...")
    role_family = classify_target_role(title)

    resume = load_master_resume()
    if not resume:
        return None

    role_profile = resume.get("role_profiles", {}).get(role_family or "", {})
    role_names = list(get_target_roles())

    prompt = f"""
    You are an expert ATS Optimization Agent.
    Target Job Title: {title}
    Company: {company}
    Target role family: {role_family or 'Choose the closest match'}
    Available role families: {', '.join(role_names)}
    Role focus: {role_profile.get('focus', 'Match the job requirements to the master resume facts.')}
    Priority keywords: {', '.join(role_profile.get('keywords', []))}

    My Master Resume Data:
    {yaml.dump(resume, default_flow_style=False)}

    Task:
    1. Identify which target role family best matches the job: {_join_choices(role_names)}.
    2. Write a 3-sentence professional summary tailored specifically to the {title} role and selected role family.
    3. Select and rephrase the 4 most relevant work experience bullet points from my master resume to highlight matching skills for {title}.
    4. CRITICAL RULE: DO NOT invent, fabricate, or assume any experience, skills, company names, or degrees not present in my master resume.

    Format your response EXACTLY as:
    SUMMARY: <your 3-sentence summary>
    BULLETS:
    - <bullet 1>
    - <bullet 2>
    - <bullet 3>
    - <bullet 4>
    """

    client = client or get_client()
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )

    tailored_text = response.choices[0].message.content
    log("\n--- Tailored AI Output ---\n")
    log(tailored_text)

    summary = ""
    bullets = []
    for line in tailored_text.strip().splitlines():
        if line.startswith("SUMMARY:"):
            summary = line.removeprefix("SUMMARY:").strip()
        elif line.strip().startswith("- "):
            bullets.append(line.strip()[2:])

    if not summary:
        summary = tailored_text.strip()

    return {"summary": summary, "bullets": bullets, "role_family": role_family or "", "raw": tailored_text}


def build_tailored_cv(job_id, summary, bullets, role_family=None, run_id=None):
    """Write the DOCX from (possibly user-edited) content and link it to the job."""
    job = get_job(job_id)
    if not job:
        log("❌ Job not found in database!", level="error")
        return None
    title, company, _location, _url = job
    role_family = role_family if role_family is not None else classify_target_role(title)
    docx_path = create_tailored_cv_docx(company, title, summary, bullets, role_family)
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
        return build_tailored_cv(job_id, content["summary"], content["bullets"], content["role_family"], run_id=run_id)

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
