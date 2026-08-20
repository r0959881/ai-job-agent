import requests
import sqlite3
import hashlib

def generate_job_id(company, title):
    raw_str = f"{company.lower().strip()}_{title.lower().strip()}"
    return hashlib.md5(raw_str.encode()).hexdigest()

def fetch_arbeitnow_jobs(keyword="data"):
    url = "https://www.arbeitnow.com/api/job-board-api"
    print(f"🔍 Searching for '{keyword}' jobs...")
    try:
        response = requests.get(url)
        data = response.json()
        conn = sqlite3.connect("jobs.db")
        cursor = conn.cursor()
        new_jobs_count = 0
        for item in data.get("data", []):
            title = item.get("title", "")
            company = item.get("company_name", "")
            if keyword.lower() in title.lower() or keyword.lower() in item.get("description", "").lower():
                job_id = generate_job_id(company, title)
                location = item.get("location", "Remote/Unspecified")
                job_url = item.get("url", "")
                try:
                    cursor.execute(
                        "INSERT INTO jobs (id, title, company, location, url, source) VALUES (?, ?, ?, ?, ?, ?)",
                        (job_id, title, company, location, job_url, "Arbeitnow")
                    )
                    new_jobs_count += 1
                except sqlite3.IntegrityError:
                    pass
        conn.commit()
        conn.close()
        print(f"🎉 Success! Found and saved {new_jobs_count} new job(s).")
    except Exception as e:
        print(f"❌ Error fetching jobs: {e}")

if __name__ == "__main__":
    fetch_arbeitnow_jobs(keyword="data")