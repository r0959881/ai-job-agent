import os
import time
import yaml
import sqlite3
from playwright.sync_api import sync_playwright

def load_standard_answers():
    """Loads default responses for standard candidate questions."""
    if not os.path.exists("resume_data.yaml"):
        return {}
    with open("resume_data.yaml", "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
        return {**data.get("personal_info", {}), **data.get("standard_answers", {})}

def auto_fill_job_application(job_url, docx_path, headless=False):
    """
    Launches Chromium, navigates to the job posting, populates basic details,
    attaches the tailored .docx resume, and pauses for user review.
    """
    answers = load_standard_answers()
    print(f"\n🤖 Launching Form Submitter for: {job_url}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=300)
        page = browser.new_page()
        
        try:
            page.goto(job_url, timeout=60000)
            page.wait_for_load_state("domcontentloaded")
            print("🌐 Page loaded. Filling available application fields...")

            # 1. Full Name
            full_name = answers.get("full_name", "")
            if full_name:
                for selector in ["input[name*='name' i]", "input[id*='name' i]", "input[placeholder*='name' i]"]:
                    locator = page.locator(selector).first
                    if locator.count() > 0 and locator.is_visible():
                        locator.fill(full_name)
                        print("  ✓ Name filled")
                        break

            # 2. Email Address
            email = answers.get("email", "")
            if email:
                for selector in ["input[type='email']", "input[name*='email' i]", "input[id*='email' i]"]:
                    locator = page.locator(selector).first
                    if locator.count() > 0 and locator.is_visible():
                        locator.fill(email)
                        print("  ✓ Email filled")
                        break

            # 3. Phone Number
            phone = answers.get("phone", "")
            if phone:
                for selector in ["input[type='tel']", "input[name*='phone' i]", "input[id*='phone' i]"]:
                    locator = page.locator(selector).first
                    if locator.count() > 0 and locator.is_visible():
                        locator.fill(phone)
                        print("  ✓ Phone filled")
                        break

            # 4. Attach Resume Document (.docx)
            if docx_path and os.path.exists(docx_path):
                file_input = page.locator("input[type='file']").first
                if file_input.count() > 0:
                    file_input.set_input_files(docx_path)
                    print(f"  ✓ Attached CV: {docx_path}")

            print("✅ Form field auto-fill completed.")
            time.sleep(5)
            browser.close()
            return True

        except Exception as e:
            print(f"⚠️ Form auto-fill warning/error: {e}")
            browser.close()
            return False

if __name__ == "__main__":
    conn = sqlite3.connect("jobs.db")
    cursor = conn.cursor()
    cursor.execute("SELECT url FROM jobs WHERE status = 'processed' LIMIT 1")
    row = cursor.fetchone()
    conn.close()

    if row:
        auto_fill_job_application(row[0], None, headless=False)
    else:
        print("⚠️ No processed jobs found in jobs.db")