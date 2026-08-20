import os
import sqlite3
import yaml
from dotenv import load_dotenv
from groq import Groq
from generate_doc import create_tailored_cv_docx

# 1. Load environment variables (.env file)
load_dotenv()

# 2. Initialize Groq client
groq_api_key = os.getenv("GROQ_API_KEY")
if not groq_api_key:
    raise SystemExit(
        "❌ GROQ_API_KEY is not configured. "
        "Copy .env.example to .env and add your Groq API key."
    )
if not groq_api_key.startswith("gsk_"):
    raise SystemExit(
        "❌ GROQ_API_KEY is invalid or still a placeholder. "
        "Create a new Groq key and set it as GROQ_API_KEY in .env."
    )
client = Groq(api_key=groq_api_key)

def load_master_resume():
    if not os.path.exists("resume_data.yaml"):
        print("❌ Error: resume_data.yaml not found!")
        return None
    with open("resume_data.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def tailor_cv_for_job(job_id):
    conn = sqlite3.connect("jobs.db")
    cursor = conn.cursor()
    cursor.execute("SELECT title, company, location, url FROM jobs WHERE id = ?", (job_id,))
    job = cursor.fetchone()
    conn.close()

    if not job:
        print("❌ Job not found in database!")
        return None

    title, company, location, url = job
    print(f"🤖 Tailoring CV for: {title} at {company}...")

    resume = load_master_resume()
    if not resume:
        return None

    prompt = f"""
    You are an expert ATS Optimization Agent.
    Target Job Title: {title}
    Company: {company}
    
    My Master Resume Data:
    {yaml.dump(resume, default_flow_style=False)}
    
    Task:
    1. Write a 3-sentence professional summary tailored specifically to the {title} role.
    2. Select and rephrase the 4 most relevant work experience bullet points from my master resume to highlight matching skills for {title}.
    3. CRITICAL RULE: DO NOT invent, fabricate, or assume any experience, skills, company names, or degrees not present in my master resume.
    
    Format your response EXACTLY as:
    SUMMARY: <your 3-sentence summary>
    BULLETS:
    - <bullet 1>
    - <bullet 2>
    - <bullet 3>
    - <bullet 4>
    """

    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )

        tailored_text = response.choices[0].message.content
        print("\n--- Tailored AI Output ---\n")
        print(tailored_text)

        summary = ""
        bullets = []
        for line in tailored_text.strip().splitlines():
            if line.startswith("SUMMARY:"):
                summary = line.removeprefix("SUMMARY:").strip()
            elif line.strip().startswith("- "):
                bullets.append(line.strip()[2:])

        if not summary:
            summary = tailored_text.strip()

        docx_path = create_tailored_cv_docx(company, title, summary, bullets)
        if not docx_path:
            return None

        conn = sqlite3.connect("jobs.db")
        conn.execute("UPDATE jobs SET status = 'processed' WHERE id = ?", (job_id,))
        conn.commit()
        conn.close()

        return docx_path

    except Exception as e:
        print(f"❌ Error communicating with Groq API: {e}")
        return None

if __name__ == "__main__":
    if os.path.exists("jobs.db"):
        conn = sqlite3.connect("jobs.db")
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