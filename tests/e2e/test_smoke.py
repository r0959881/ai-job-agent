"""End-to-end smoke test: edit profile -> mocked run -> open a job -> mark it applied.

Runs the real server (built web/dist) against a throwaway data root with
AI_JOB_AGENT_FAKE_SOURCES=1, drives it with Playwright, and runs an axe
accessibility scan on every main page in light and dark mode.

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
import yaml

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
    shutil.copy(CODE_ROOT / "resume_data.yaml", root / "resume_data.yaml")
    port = free_port()
    env = {**os.environ, "AI_JOB_AGENT_ROOT": str(root), "AI_JOB_AGENT_FAKE_SOURCES": "1",
           "AI_JOB_AGENT_FAKE_GROQ_DELAY": "0.2"}
    for key in ("GROQ_API_KEY", "ADZUNA_APP_ID", "ADZUNA_APP_KEY"):
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


def test_profile_run_job_applied(server, browser):
    base, root = server
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))

    # 1. Edit the profile
    page.goto(f"{base}/profile")
    page.get_by_label("Headline").fill("Data Engineer (e2e)")
    page.get_by_role("button", name="Save", exact=True).click()
    page.get_by_text("Profile saved").wait_for()
    assert yaml.safe_load((root / "resume_data.yaml").read_text(encoding="utf-8"))["personal_info"]["headline"] == "Data Engineer (e2e)"

    # 2. Start a mocked run and wait for it to finish
    page.get_by_role("button", name="Run agent").first.click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_label("Max CVs to tailor").fill("2")
    dialog.get_by_role("button", name="Start run").click()
    page.wait_for_url("**/runs/*")
    page.get_by_text("Documents from this run").wait_for(timeout=60_000)
    playwright.expect(page.get_by_text("Succeeded").first).to_be_visible()

    # 3. Open a job that is ready to apply and mark it applied
    page.goto(f"{base}/jobs?quick=ready")
    page.get_by_role("table").wait_for()
    page.get_by_role("row").nth(1).click()
    page.wait_for_url("**/jobs/*")
    job_id = page.url.rsplit("/", 1)[-1]
    page.get_by_role("button", name="I applied manually").click()
    page.get_by_text("Marked as applied").wait_for()
    with urllib.request.urlopen(f"{base}/api/jobs/{job_id}") as response:
        job = json.load(response)
    assert job["application_status"] == "applied" and job["applied_at"]
    assert not errors, errors


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_main_pages_have_no_serious_accessibility_violations(server, browser, scheme):
    if not AXE.exists():
        pytest.skip("axe-core is not installed (cd web && npm install)")
    base, _root = server
    page = browser.new_page(viewport={"width": 1280, "height": 900}, color_scheme=scheme)
    with urllib.request.urlopen(f"{base}/api/jobs?page_size=1") as response:
        first_job = json.load(response)["items"]
    paths = ["/", "/profile", "/jobs", "/documents", "/runs", "/settings/search", "/settings/integrations", "/onboarding"]
    if first_job:
        paths.append(f"/jobs/{first_job[0]['id']}")
    problems = {}
    for path in paths:
        page.goto(base + path)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(300)
        violations = axe_violations(page)
        if violations:
            problems[path] = violations
    assert not problems, "\n".join(f"{path}: {item}" for path, items in problems.items() for item in items)
