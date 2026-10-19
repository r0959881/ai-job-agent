"""Phase 1: config, settings, logger, migrations, backfill and the API skeleton."""
import importlib
import shutil
import sqlite3
import threading
from contextlib import closing

import pytest
from conftest import CODE_ROOT

import agent_settings
import config
from agent_log import RunCancelled, check_cancelled, event_scope, log, step


def test_paths_are_anchored_to_the_project_root(project_root):
    assert config.DB_PATH == project_root / "jobs.db"
    assert config.OUTPUT_DIR == project_root / "output"
    assert config.resolve_project_path("output/x.docx") == project_root / "output" / "x.docx"
    assert config.relative_to_project(project_root / "output" / "x.docx") == "output/x.docx"


def test_file_name_slug_comes_from_the_resume():
    assert config.file_name_slug() == "Ammar_Haider"
    assert config.file_name_slug("Jane  van Dam") == "Jane_van_Dam"
    assert config.file_name_slug("") == "Candidate"


def test_atomic_write_replaces_and_leaves_no_temp_files(project_root):
    target = project_root / "a.txt"
    config.atomic_write_text(target, "one")
    config.atomic_write_text(target, "two")
    assert target.read_text() == "two"
    assert [p.name for p in project_root.iterdir() if p.name.startswith(".a.txt")] == []


def test_settings_defaults_match_the_old_constants():
    import discovery

    settings = agent_settings.load()
    assert settings["target_roles"] == discovery.TARGET_ROLES
    assert agent_settings.all_target_keywords(settings) == discovery.TARGET_KEYWORDS
    assert settings["time_window_hours"] == 48
    assert agent_settings.gmail_query(settings) == (
        'newer_than:2d {from:linkedin.com from:indeed.com '
        'from:stepstone.be from:jobat.be from:vdab.be from:actiris.brussels}'
    )


def test_settings_file_overrides_and_falls_back(project_root):
    agent_settings.save({"time_window_hours": 24, "gmail": {"lookback_days": 1}})
    settings = agent_settings.load()
    assert settings["time_window_hours"] == 24
    assert settings["gmail"]["lookback_days"] == 1
    assert settings["gmail"]["senders"][0] == "linkedin.com"  # merged with defaults
    assert settings["allowed_locations"] == agent_settings.DEFAULTS["allowed_locations"]


def test_settings_change_the_relevance_filter(project_root):
    from discovery import is_relevant_job

    assert is_relevant_job("Junior Data Engineer", "", "Antwerp")
    agent_settings.save({"allowed_locations": ["paris"], "blocked_locations": []})
    assert not is_relevant_job("Junior Data Engineer", "", "Antwerp")
    assert is_relevant_job("Junior Data Engineer", "", "Paris")


def test_seed_writes_the_file_once(project_root):
    assert agent_settings.seed(cover_letters={"X": {"opening": "a"}})
    assert not agent_settings.seed()
    assert agent_settings.load()["cover_letters"] == {"X": {"opening": "a"}}


def test_logger_prints_and_emits(capsys):
    events = []
    with event_scope(lambda *args: events.append(args)):
        step("adzuna", "started", "go")
        log("hello")
    log("outside")
    assert capsys.readouterr().out == "hello\noutside\n"
    assert events == [("adzuna", "started", "go", {}), ("adzuna", "log", "hello", {"level": "info"})]


def test_cancellation_is_cooperative():
    cancel = threading.Event()
    with event_scope(None, cancel):
        check_cancelled()
        cancel.set()
        with pytest.raises(RunCancelled):
            check_cancelled()
    check_cancelled()  # Outside a scope nothing is cancelled.


def test_tailor_imports_without_a_groq_key():
    import tailor

    importlib.reload(tailor)
    with pytest.raises(tailor.GroqConfigError, match="GROQ_API_KEY is not configured"):
        tailor.get_client()


def test_migrations_are_idempotent_on_a_copy_of_the_real_db(project_root):
    from database import init_db

    real_db = CODE_ROOT / "jobs.db"
    if not real_db.exists():
        pytest.skip("No jobs.db in the project to copy")
    shutil.copy(real_db, config.DB_PATH)
    with closing(sqlite3.connect(config.DB_PATH)) as conn:
        before = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    init_db()
    init_db()
    with closing(sqlite3.connect(config.DB_PATH)) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        after = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        statuses = {row[0] for row in conn.execute("SELECT DISTINCT application_status FROM jobs")}
    assert {"role_family", "application_status", "applied_at", "notes", "cover_letter_path"} <= columns
    assert {"jobs", "runs", "documents"} <= tables
    assert after == before
    assert statuses <= {"not_applied"}


def test_backfill_links_files_to_jobs(project_root):
    from api.services.documents import backfill_documents
    from database import init_db, transaction

    init_db()
    with transaction() as conn:
        conn.execute("INSERT INTO jobs (id, title, company, location) VALUES ('j1', 'Junior Data Engineer', 'Acme', 'Gent')")
    out = project_root / "output"
    (out / "Ammar_Haider_CV_Acme_Junior Data Engineer.docx").write_bytes(b"x")
    (out / "Ammar_Haider_CV_Sample_Data Analyst.docx").write_bytes(b"x")
    (out / "Ammar_Haider_Cover_Letter_Data Engineer.docx").write_bytes(b"x")
    (out / "job_report_20260101_000000.xlsx").write_bytes(b"x")

    counts = backfill_documents()
    assert counts["added"] == 4 and counts["linked"] == 1
    assert backfill_documents()["added"] == 0  # idempotent
    with transaction() as conn:
        rows = {r[0]: r[1:] for r in conn.execute("SELECT path, kind, job_id, role_family FROM documents")}
    assert rows["output/Ammar_Haider_CV_Acme_Junior Data Engineer.docx"] == ("cv", "j1", "Data Engineer")
    assert rows["output/Ammar_Haider_CV_Sample_Data Analyst.docx"] == ("cv", None, "Data Analyst")
    assert rows["output/Ammar_Haider_Cover_Letter_Data Engineer.docx"] == ("cover_letter", None, "Data Engineer")
    assert rows["output/job_report_20260101_000000.xlsx"][0] == "report"

    (out / "job_report_20260101_000000.xlsx").unlink()
    assert backfill_documents()["removed"] == 1


def test_health_and_session(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/session").json()["token"] == client.headers["X-UI-Token"]


def test_mutations_need_the_ui_token(client):
    response = client.post("/api/runs", json={}, headers={"X-UI-Token": "wrong"})
    assert response.status_code == 403
    response = client.post("/api/runs", json={}, headers={"Origin": "http://evil.example"})
    assert response.status_code == 403


def test_only_localhost_hosts_are_served():
    from fastapi.testclient import TestClient

    from api.app import create_app

    with TestClient(create_app(run_startup=False), base_url="http://attacker.example") as other:
        assert other.get("/api/health").status_code == 400


def test_unknown_api_paths_return_json_404(client):
    response = client.get("/api/nope")
    assert response.status_code == 404
    assert "No API endpoint" in response.json()["detail"]
