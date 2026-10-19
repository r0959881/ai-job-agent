import time

from agent_log import log
from config import load_resume_file, resolve_project_path
from database import connect

def load_standard_answers():
    """Loads default responses for standard candidate questions."""
    data = load_resume_file()
    if data is None:
        return {}
    return {**data.get("personal_info", {}), **data.get("standard_answers", {})}

def auto_fill_job_application(job_url, docx_path, headless=False, keep_open_seconds=5, report=False,
                              on_filled=None, wait_for_close=False):
    """
    Launches Chromium, navigates to the job posting, populates basic details,
    attaches the tailored .docx resume, and pauses for user review.

    With report=True a dict {"ok", "filled", "error"} is returned instead of a bool.
    on_filled(result) is called as soon as filling finishes; wait_for_close keeps the
    window open until the user closes it (the web UI uses both so you can submit yourself).
    """
    from playwright.sync_api import sync_playwright

    answers = load_standard_answers()
    filled = []
    log(f"\n🤖 Launching Form Submitter for: {job_url}")
    if docx_path:
        docx_path = str(resolve_project_path(docx_path))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=300)
        page = browser.new_page()

        try:
            page.goto(job_url, timeout=60000)
            page.wait_for_load_state("domcontentloaded")
            log("🌐 Page loaded. Filling available application fields...")

            # 1. Full Name
            full_name = answers.get("full_name", "")
            if full_name:
                for selector in ["input[name*='name' i]", "input[id*='name' i]", "input[placeholder*='name' i]"]:
                    locator = page.locator(selector).first
                    if locator.count() > 0 and locator.is_visible():
                        locator.fill(full_name)
                        filled.append("name")
                        log("  ✓ Name filled")
                        break

            # 2. Email Address
            email = answers.get("email", "")
            if email:
                for selector in ["input[type='email']", "input[name*='email' i]", "input[id*='email' i]"]:
                    locator = page.locator(selector).first
                    if locator.count() > 0 and locator.is_visible():
                        locator.fill(email)
                        filled.append("email")
                        log("  ✓ Email filled")
                        break

            # 3. Phone Number
            phone = answers.get("phone", "")
            if phone:
                for selector in ["input[type='tel']", "input[name*='phone' i]", "input[id*='phone' i]"]:
                    locator = page.locator(selector).first
                    if locator.count() > 0 and locator.is_visible():
                        locator.fill(phone)
                        filled.append("phone")
                        log("  ✓ Phone filled")
                        break

            # 4. Attach Resume Document (.docx)
            if docx_path and resolve_project_path(docx_path).exists():
                file_input = page.locator("input[type='file']").first
                if file_input.count() > 0:
                    file_input.set_input_files(docx_path)
                    filled.append("cv")
                    log(f"  ✓ Attached CV: {docx_path}")

            log("✅ Form field auto-fill completed.")
            if on_filled:
                on_filled({"ok": True, "filled": filled})
            if wait_for_close:
                page.wait_for_event("close", timeout=0)
            elif keep_open_seconds:
                time.sleep(keep_open_seconds)
            browser.close()
            return {"ok": True, "filled": filled} if report else True

        except Exception as e:
            log(f"⚠️ Form auto-fill warning/error: {e}", level="warning")
            if on_filled:
                on_filled({"ok": False, "filled": filled, "error": str(e)})
            browser.close()
            return {"ok": False, "filled": filled, "error": str(e)} if report else False

if __name__ == "__main__":
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT url FROM jobs WHERE status = 'processed' LIMIT 1")
    row = cursor.fetchone()
    conn.close()

    if row:
        auto_fill_job_application(row[0], None, headless=False)
    else:
        print("⚠️ No processed jobs found in jobs.db")
