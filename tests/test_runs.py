"""Run manager and /api/runs: lifecycle, SSE, conflicts and cancellation (sources mocked)."""
import json
import threading

from helpers import FakeGroq, install_fakes


def wait_for(client, run_id, timeout=30):
    client.app.state.runs.wait(run_id, timeout)
    return client.get(f"/api/runs/{run_id}").json()


def test_a_run_completes_and_is_recorded(client, monkeypatch):
    install_fakes(monkeypatch)
    response = client.post("/api/runs", json={"sources": ["adzuna", "arbeitnow", "gmail"]})
    assert response.status_code == 201
    run = wait_for(client, response.json()["id"])

    assert run["status"] == "succeeded"
    assert run["tailored"] > 0 and run["new"] > 0 and run["failed"] == 0
    steps = {s["step"]: s for s in run["steps"]}
    assert all(steps[name]["status"] == "succeeded" for name in ("init_db", "adzuna", "arbeitnow", "gmail", "report"))
    assert steps["tailoring"]["data"]["done"] == steps["tailoring"]["data"]["total"] == run["tailored"]
    assert run["duration_seconds"] is not None
    kinds = [doc["kind"] for doc in run["documents"]]
    assert kinds.count("cv") == run["tailored"] and "report" in kinds

    log = client.get(f"/api/runs/{run['id']}/log").text
    assert "Running AI Job Agent Pipeline" in log and "Excel report created" in log

    listing = client.get("/api/runs").json()
    assert listing["active_id"] is None and listing["items"][0]["id"] == run["id"]


def test_sse_replays_every_event_then_ends(client, monkeypatch):
    install_fakes(monkeypatch)
    run_id = client.post("/api/runs", json={"dry_run": True}).json()["id"]
    wait_for(client, run_id)
    with client.stream("GET", f"/api/runs/{run_id}/events") as stream:
        body = "".join(stream.iter_text())
    events = [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: {\"")]
    assert events[0]["seq"] == 1
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert events[-1]["status"] == "finished"
    assert "event: end" in body

    with client.stream("GET", f"/api/runs/{run_id}/events", headers={"Last-Event-ID": str(len(events) - 2)}) as stream:
        resumed = [line for line in "".join(stream.iter_text()).splitlines() if line.startswith("data: {\"")]
    assert len(resumed) == 2


def test_only_one_run_at_a_time_and_cancel_mid_tailoring(client, monkeypatch):
    gate = threading.Event()
    entered = threading.Event()

    def block_on_first_call(count):
        if count == 1:
            entered.set()
            gate.wait(10)

    install_fakes(monkeypatch, groq=FakeGroq(on_call=block_on_first_call))
    run_id = client.post("/api/runs", json={}).json()["id"]
    assert entered.wait(15), "tailoring never started"

    conflict = client.post("/api/runs", json={})
    assert conflict.status_code == 409 and conflict.json()["detail"]["run_id"] == run_id
    assert client.get("/api/runs").json()["active_id"] == run_id

    assert client.post(f"/api/runs/{run_id}/cancel").status_code == 200
    gate.set()
    run = wait_for(client, run_id)
    assert run["status"] == "cancelled"
    tailoring = next(s for s in run["steps"] if s["step"] == "tailoring")
    assert tailoring["data"]["done"] == 1  # stopped right after the job in progress
    assert client.post(f"/api/runs/{run_id}/cancel").status_code == 409


def test_failures_are_reported_not_raised(client, monkeypatch):
    install_fakes(monkeypatch)

    def boom(*_args, **_kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr("main.export_jobs_to_excel", boom)
    run = wait_for(client, client.post("/api/runs", json={"dry_run": True}).json()["id"])
    assert run["status"] == "failed" and "disk full" in run["error"]


def test_invalid_options_are_rejected(client):
    assert client.post("/api/runs", json={"sources": ["myspace"]}).status_code == 422
    assert client.post("/api/runs", json={"sources": []}).status_code == 422
    assert client.post("/api/runs", json={"time_window_hours": 0}).status_code == 422
    assert client.get("/api/runs/999").status_code == 404


def test_interrupted_runs_are_marked_failed(project_root):
    from api.services.runs import mark_interrupted_runs
    from database import init_db, transaction

    init_db()
    with transaction() as conn:
        conn.execute("INSERT INTO runs (started_at, status) VALUES ('2026-01-01T00:00:00+00:00', 'running')")
    mark_interrupted_runs()
    with transaction() as conn:
        assert conn.execute("SELECT status FROM runs").fetchone()[0] == "failed"
