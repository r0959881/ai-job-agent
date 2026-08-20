import os
import sqlite3
import yaml
from dotenv import load_dotenv
from groq import Groq

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
    """

    try:
        # Active supported Groq model
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )

        tailored_text = response.choices[0].message.content
        print("\n--- Tailored AI Output ---\n")
        print(tailored_text)

        os.makedirs("output", exist_ok=True)
        clean_company = "".join(c for c in company if c.isalnum() or c in (' ', '_')).rstrip()
        clean_title = "".join(c for c in title if c.isalnum() or c in (' ', '_')).rstrip()
        filename = f"output/Tailored_{clean_company.replace(' ', '_')}_{clean_title.replace(' ', '_')}.txt"
        
        with open(filename, "w", encoding="utf-8") as f:
            f.write(tailored_text)

        print(f"\n✅ Saved tailored document to: {filename}")
        return tailored_text

    except Exception as e:
        print(f"❌ Error communicating with Groq API: {e}")
        return None

if __name__ == "__main__":
    if os.path.exists("jobs.db"):
        conn = sqlite3.connect("jobs.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM jobs LIMIT 1")
        first_job = cursor.fetchone()
        conn.close()

        if first_job:
            tailor_cv_for_job(first_job[0])
        else:
            print("⚠️ No jobs found in database. Run 'python discovery.py' first!")
    else:
        print("⚠️ jobs.db does not exist yet. Run 'python database.py' and 'python discovery.py' first!")