"""Point every module at a throwaway project root before anything is imported."""
import os
import shutil
import sys
import tempfile
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parents[1]
TEST_ROOT = Path(tempfile.mkdtemp(prefix="ai_job_agent_tests_")).resolve()
os.environ["AI_JOB_AGENT_ROOT"] = str(TEST_ROOT)
os.environ["AI_JOB_AGENT_DEV_LOGIN"] = "1"
for key in ("GROQ_API_KEY", "GROQ_API_KEY_2", "BRAVE_API_KEY", "ADZUNA_APP_ID", "ADZUNA_APP_KEY", "ALERT_EMAIL_FROM",
            "ALERT_EMAIL_PASS", "ALERT_EMAIL_TO", "DATABASE_URL", "SECRET_KEY", "PUBLIC_URL", "ALLOWED_EMAILS", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET",
            "LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET", "AI_JOB_AGENT_FAKE_SOURCES"):
    os.environ.pop(key, None)
# .env is read from the test root (which has none), so real secrets are never loaded.
sys.path.insert(0, str(CODE_ROOT))

import pytest  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TEST_EMAIL = "tester@example.com"


def _reset_root():
    from api import store

    store.reset_engine()
    for child in TEST_ROOT.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink()
    shutil.copy(CODE_ROOT / "resume_data.yaml", TEST_ROOT / "resume_data.yaml")
    (TEST_ROOT / "output").mkdir()


@pytest.fixture(autouse=True)
def project_root():
    """A fresh project folder (resume copied, empty output/) and an empty server database for every test."""
    _reset_root()
    yield TEST_ROOT
    for key in ("GROQ_API_KEY", "GROQ_API_KEY_2", "BRAVE_API_KEY", "ADZUNA_APP_ID", "ADZUNA_APP_KEY"):
        os.environ.pop(key, None)


def sign_in(test_client, email=TEST_EMAIL, name="Test User"):
    """Sign in through the developer login and send the CSRF token on every later request."""
    csrf = test_client.get("/api/session").json()["csrf"]
    response = test_client.post("/api/auth/dev/login", json={"email": email, "name": name},
                                headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200, response.text
    test_client.headers["X-CSRF-Token"] = response.json()["csrf"]
    return response.json()["user"]


@pytest.fixture
def anon_client():
    from fastapi.testclient import TestClient

    from api.app import create_app

    with TestClient(create_app(), base_url="http://127.0.0.1") as test_client:
        yield test_client


@pytest.fixture
def client(anon_client):
    """Signed in as a test user whose resume is a copy of resume_data.yaml."""
    from api import store

    user = sign_in(anon_client)
    store.set_resume_text(user["id"], (CODE_ROOT / "resume_data.yaml").read_text(encoding="utf-8"))
    anon_client.user = user
    yield anon_client


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(TEST_ROOT, ignore_errors=True)
