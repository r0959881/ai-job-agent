"""Point every module at a throwaway project root before anything is imported."""
import os
import shutil
import sys
import tempfile
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parents[1]
TEST_ROOT = Path(tempfile.mkdtemp(prefix="ai_job_agent_tests_")).resolve()
os.environ["AI_JOB_AGENT_ROOT"] = str(TEST_ROOT)
for key in ("GROQ_API_KEY", "ADZUNA_APP_ID", "ADZUNA_APP_KEY", "ALERT_EMAIL_FROM", "ALERT_EMAIL_PASS", "ALERT_EMAIL_TO"):
    os.environ.pop(key, None)
# .env is read from the test root (which has none), so real secrets are never loaded.
sys.path.insert(0, str(CODE_ROOT))

import pytest  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _reset_root():
    for child in TEST_ROOT.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink()
    shutil.copy(CODE_ROOT / "resume_data.yaml", TEST_ROOT / "resume_data.yaml")
    (TEST_ROOT / "output").mkdir()


@pytest.fixture(autouse=True)
def project_root():
    """A fresh project folder (resume copied, empty output/) for every test."""
    _reset_root()
    yield TEST_ROOT
    for key in ("GROQ_API_KEY", "ADZUNA_APP_ID", "ADZUNA_APP_KEY"):
        os.environ.pop(key, None)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from api.app import create_app
    from api.security import get_ui_token

    app = create_app(run_startup=False)
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        test_client.headers["X-UI-Token"] = get_ui_token()
        yield test_client


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(TEST_ROOT, ignore_errors=True)
