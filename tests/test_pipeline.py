"""The pipeline with mocked sources: events, skips and cancellation."""
import threading

import pytest
from helpers import FakeGroq, install_fakes

import agent_settings
from agent_log import RunCancelled


def collect():
    events = []
    return events, lambda step, status, message, data: events.append((step, status, message, data))


def test_full_run_emits_every_step(monkeypatch, capsys):
    import main

    groq = install_fakes(monkeypatch)
    events, on_event = collect()
    summary = main.run_agent(on_event=on_event, interactive=False)

    finished = {(step, status) for step, status, *_ in events if status not in {"log", "progress"}}
    # The default regions (Belgium, Netherlands) have VDAB as their key-less job board.
    for step in ("init_db", "scrape", "boards", "adzuna", "gmail", "filter", "tailoring", "report"):
        assert (step, "succeeded") in finished, step
    assert summary["tailored"] == groq.completions.calls == summary["eligible"] > 0
    assert summary["failed"] == 0
    assert summary["report_path"].startswith("output/job_report_")
    out = capsys.readouterr().out
    assert "🚀 Running AI Job Agent Pipeline" in out and "📊 Excel report created" in out


def test_cli_without_listener_prints_the_same_lines(monkeypatch, capsys):
    import main

    install_fakes(monkeypatch)
    main.run_agent()
    out = capsys.readouterr().out
    assert out.count("✅ Database initialized successfully!") >= 2
    assert "🎯 [Adzuna Belgium] Saved 1 job(s) | (0 duplicates, 1 filtered)" in out
    assert "✅ Included" in out and "from the last 24 hours." in out


def test_missing_groq_key_skips_tailoring_with_a_warning(monkeypatch):
    import main

    install_fakes(monkeypatch)
    monkeypatch.delenv("GROQ_API_KEY")
    events, on_event = collect()
    summary = main.run_agent(on_event=on_event, interactive=False)
    tailoring = [e for e in events if e[0] == "tailoring" and e[1] == "skipped"]
    assert tailoring and tailoring[0][3]["action"] == "configure_groq"
    assert summary["tailored"] == 0
    assert any(e[0] == "report" and e[1] == "succeeded" for e in events)


def test_groq_failures_are_counted_with_a_reason(monkeypatch):
    import main

    install_fakes(monkeypatch, groq=FakeGroq(fail=TimeoutError("Request timed out")))
    events, on_event = collect()
    summary = main.run_agent(on_event=on_event, interactive=False, options={"max_tailor": 2})
    assert summary["failed"] == 2
    assert {f["reason"] for f in summary["failures"]} == {"Groq timed out"}
    final = [e for e in events if e[0] == "tailoring" and e[1] == "warning"][0]
    assert final[2] == "Tailored 0 of 2 CVs. 2 failed: Groq timed out."


def test_gmail_reauth_is_skipped_without_opening_a_browser(monkeypatch, project_root):
    from google.auth.exceptions import RefreshError

    import gmail_parser
    import main

    install_fakes(monkeypatch, gmail=False)

    class ExpiredCreds:
        valid = False
        expired = True
        refresh_token = "r"

        def refresh(self, _request):
            raise RefreshError("invalid_grant: Token has been expired or revoked.")

    (project_root / "token.json").write_text("{}")
    monkeypatch.setattr(gmail_parser.Credentials, "from_authorized_user_file", lambda *a, **k: ExpiredCreds())

    def no_browser(*_a, **_k):
        raise AssertionError("The server path must never open a browser")

    monkeypatch.setattr(gmail_parser.InstalledAppFlow, "from_client_secrets_file", no_browser)
    events, on_event = collect()
    summary = main.run_agent(on_event=on_event, interactive=False, options={"dry_run": True})
    gmail = [e for e in events if e[0] == "gmail" and e[1] == "warning"]
    assert gmail and gmail[0][3]["action"] == "reconnect_gmail"
    assert gmail[0][3]["gmail_status"] == "reauth_required"
    assert gmail_parser.read_gmail_state()["status"] == "reauth_required"
    assert summary["new"] > 0  # the other sources still ran


def test_options_limit_sources_window_and_dry_run(monkeypatch):
    import main

    groq = install_fakes(monkeypatch)
    events, on_event = collect()
    main.run_agent(on_event=on_event, interactive=False,
                   options={"sources": ["arbeitnow"], "time_window_hours": 1, "dry_run": True})
    statuses = {(e[0], e[1]) for e in events}
    assert ("adzuna", "skipped") in statuses and ("gmail", "skipped") in statuses
    assert ("scrape", "skipped") in statuses
    assert ("tailoring", "skipped") in statuses
    assert groq.completions.calls == 0


def test_cancel_mid_tailoring_stops_before_the_next_job(monkeypatch):
    import main

    cancel = threading.Event()
    groq = install_fakes(monkeypatch, groq=FakeGroq(on_call=lambda n: cancel.set() if n == 2 else None))
    with pytest.raises(RunCancelled):
        main.run_agent(cancel_event=cancel, interactive=False)
    assert groq.completions.calls == 2


def test_settings_edits_apply_to_the_next_run(monkeypatch):
    import main

    install_fakes(monkeypatch)
    agent_settings.save({"regions": ["BE"], "target_roles": {"Data Engineer": ["data engineer"]},
                         "search_queries": {"Data Engineer": ["data engineer"]}})
    events, on_event = collect()
    main.run_agent(on_event=on_event, interactive=False, options={"dry_run": True})
    progress = [e for e in events if e[0] == "adzuna" and e[1] == "progress"]
    assert progress[-1][3]["total"] == 1
