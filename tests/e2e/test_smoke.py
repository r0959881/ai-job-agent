"""End-to-end smoke test: sign in -> edit profile -> mocked run -> open a job -> mark it applied.

Runs the real server (built web/dist) against a throwaway data root with
AI_JOB_AGENT_FAKE_SOURCES=1 and the developer sign-in, drives it with Playwright,
and runs an axe accessibility scan on every main page in light and dark mode.
Headless Chromium cannot answer the folder picker, so files go to browser storage.

    python -m pytest tests/e2e -m e2e        (or: cd web && npm run e2e)
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest

CODE_ROOT = Path(__file__).resolve().parents[2]
DIST = CODE_ROOT / "web" / "dist" / "index.html"
AXE = CODE_ROOT / "web" / "node_modules" / "axe-core" / "axe.min.js"

pytestmark = pytest.mark.e2e
playwright = pytest.importorskip("playwright.sync_api")


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def server():
    if not DIST.exists():
        pytest.skip("Build the web app first: cd web && npm run build")
    root = Path(tempfile.mkdtemp(prefix="ai_job_agent_e2e_"))
    port = free_port()
    env = {**os.environ, "AI_JOB_AGENT_ROOT": str(root), "AI_JOB_AGENT_FAKE_SOURCES": "1",
           "AI_JOB_AGENT_FAKE_GROQ_DELAY": "0.2", "AI_JOB_AGENT_DEV_LOGIN": "1",
           "AI_JOB_AGENT_LOCAL": "0"}
    for key in ("GROQ_API_KEY", "ADZUNA_APP_ID", "ADZUNA_APP_KEY", "DATABASE_URL", "PUBLIC_URL", "SECRET_KEY"):
        env.pop(key, None)
    process = subprocess.Popen([sys.executable, "serve.py", "--no-browser", "--port", str(port)], cwd=CODE_ROOT,
                               env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"{base}/api/health", timeout=1) as response:
                if json.load(response)["fake_sources"]:
                    break
        except OSError:
            time.sleep(0.5)
    else:
        process.kill()
        pytest.fail("The server did not start")
    yield base, root
    process.kill()
    process.wait(10)
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        instance = p.chromium.launch()
        yield instance
        instance.close()


def sign_in(context, base, email, seed_resume=True):
    page = context.new_page()
    page.goto(f"{base}/settings")
    page.wait_for_url("**/login**")
    page.get_by_label("Developer sign-in (local only)").fill(email)
    page.get_by_role("button", name="Sign in without a provider").click()
    page.wait_for_url(lambda url: "/login" not in url)
    if seed_resume:
        csrf = page.request.get(f"{base}/api/session").json()["csrf"]
        text = (CODE_ROOT / "resume_data.yaml").read_text(encoding="utf-8")
        response = page.request.put(f"{base}/api/resume/raw", data={"text": text}, headers={"X-CSRF-Token": csrf})
        assert response.ok, response.text()
    return page


def axe_violations(page):
    page.add_script_tag(path=str(AXE))
    result = page.evaluate(
        """async () => {
            const r = await axe.run(document, { runOnly: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'] });
            return r.violations.filter(v => ['serious', 'critical'].includes(v.impact))
                .map(v => `${v.id}: ${v.nodes.slice(0, 2).map(n => n.failureSummary.split('\\n')[1] + ' @ ' + n.html.slice(0, 90)).join(' | ')}`);
        }"""
    )
    return result


def test_sign_in_profile_run_job_applied(server, browser):
    base, _root = server
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = sign_in(context, base, "e2e@example.com")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))

    # 1. Edit the profile (saved in the server database)
    page.goto(f"{base}/profile")
    page.get_by_label("Headline").fill("Data Engineer (e2e)")
    page.get_by_role("button", name="Save", exact=True).click()
    page.get_by_text("Profile saved").wait_for()
    assert page.request.get(f"{base}/api/resume").json()["data"]["personal_info"]["headline"] == "Data Engineer (e2e)"

    # 2. Start a mocked run, driven by this tab, and wait for it to finish
    page.goto(f"{base}/")
    page.get_by_role("button", name="Run agent").first.click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_role("button", name="Belgium").wait_for()
    dialog.get_by_role("button", name="Next").click()
    dialog.get_by_text("Which roles should it search").wait_for()
    dialog.get_by_role("button", name="Next").click()
    dialog.get_by_label("Max CVs to tailor").fill("2")
    dialog.get_by_role("button", name="Start run").click()
    page.wait_for_url("**/runs/*")
    page.get_by_text("Documents from this run").wait_for(timeout=90_000)
    playwright.expect(page.get_by_text("Succeeded").first).to_be_visible()

    # 3. The jobs the run found are on the New jobs page, the "Added" filters find them, and Jobs
    #    (older jobs only) points to them
    for added in ("run", "", "1h"):
        page.goto(f"{base}/jobs/new?sort=discovered&added={added}")
        page.get_by_role("table").wait_for()
        assert page.get_by_role("row").count() > 1, added
    playwright.expect(page.get_by_role("columnheader", name="Added")).to_be_visible()
    playwright.expect(page.get_by_text("New", exact=True).first).to_be_visible()
    page.goto(f"{base}/jobs")
    page.get_by_text("View new jobs").wait_for()

    # 4. Open a job that is ready to apply and mark it applied
    page.goto(f"{base}/jobs/new?quick=ready")
    page.get_by_role("table").wait_for()
    page.get_by_role("row").nth(1).click()
    page.wait_for_url("**/jobs/*")
    page.get_by_role("button", name="I applied").click()
    page.get_by_text("Marked as applied").wait_for()

    # 5. The tailored CV (a PDF) is on this device and opens in the browser's PDF viewer
    page.goto(f"{base}/documents")
    page.get_by_role("button", name="Preview").first.click()
    page.get_by_role("dialog").locator("iframe").wait_for(timeout=20_000)  # the PDF in the browser viewer
    assert not errors, errors

    # 6. Jobs stay on the device: the server has no job endpoint, and another user sees nothing
    other = sign_in(browser.new_context(viewport={"width": 1280, "height": 900}), base, "other@example.com")
    other.goto(f"{base}/jobs/new")
    other.get_by_text("No new jobs in the last 24 hours").wait_for()


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_main_pages_have_no_serious_accessibility_violations(server, browser, scheme):
    if not AXE.exists():
        pytest.skip("axe-core is not installed (cd web && npm install)")
    base, _root = server
    context = browser.new_context(viewport={"width": 1280, "height": 900}, color_scheme=scheme)
    login = context.new_page()
    login.goto(f"{base}/login")
    login.wait_for_load_state("networkidle")
    problems = {}
    if violations := axe_violations(login):
        problems["/login"] = violations
    page = sign_in(context, base, f"a11y-{scheme}@example.com")
    paths = ["/", "/profile", "/jobs", "/jobs/new", "/documents", "/runs", "/settings/search", "/settings/integrations",
             "/settings/storage", "/settings/account", "/onboarding"]
    for path in paths:
        page.goto(base + path)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(300)
        violations = axe_violations(page)
        if violations:
            problems[path] = violations
    assert not problems, "\n".join(f"{path}: {item}" for path, items in problems.items() for item in items)
