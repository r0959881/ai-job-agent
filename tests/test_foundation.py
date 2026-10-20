"""Config, settings, logger and the command-line database migrations."""
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
    with pytest.raises(tailor.GroqConfigError, match="No Groq API key is set"):
        tailor.get_client()


def test_migrations_are_idempotent_on_a_copy_of_the_real_db(project_root):
    from database import init_db

    real_db = CODE_ROOT / "jobs.db"
    if not real_db.exists():
        pytest.skip("No jobs.db in the project to copy")
    shutil.copy(real_db, config.DB_PATH)
    with closing(sqlite3.connect(config.DB_PATH)) as conn:
        before = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        columns_before = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
        statuses_before = ({row[0] for row in conn.execute("SELECT DISTINCT application_status FROM jobs")}
                           if "application_status" in columns_before else {"not_applied"})
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
    assert statuses == statuses_before  # migrating never changes what the user recorded


def test_log_survives_a_console_that_cannot_print_emoji(monkeypatch):
    import builtins

    real_print = builtins.print
    printed = []

    def strict_print(message="", **kwargs):
        if any(ord(c) > 127 for c in str(message)):
            raise UnicodeEncodeError("charmap", str(message), 0, 1, "character maps to <undefined>")
        printed.append(message)

    monkeypatch.setattr(builtins, "print", strict_print)
    try:
        log("🚀 Running")
    finally:
        monkeypatch.setattr(builtins, "print", real_print)
    assert printed == ["? Running"]
