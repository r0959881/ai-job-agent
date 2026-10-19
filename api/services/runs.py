"""Run the pipeline in a background thread, one run at a time, with live events."""
import json
import threading
import traceback
from datetime import UTC, datetime

from agent_log import RunCancelled
from config import RUNS_DIR, relative_to_project, resolve_project_path
from database import init_db, transaction

STEPS = ["init_db", "adzuna", "arbeitnow", "gmail", "filter", "tailoring", "report"]
STEP_LABELS = {
    "init_db": "Init DB", "adzuna": "Adzuna", "arbeitnow": "Arbeitnow", "gmail": "Gmail",
    "filter": "Filter", "tailoring": "Tailoring", "report": "Report",
}


def _now():
    return datetime.now(UTC).isoformat()


class RunConflict(Exception):
    def __init__(self, run_id):
        super().__init__(f"Run {run_id} is still in progress. Wait for it to finish or cancel it first.")
        self.run_id = run_id


class RunState:
    def __init__(self, run_id, log_path, events_path):
        self.id = run_id
        self.log_path = log_path
        self.events_path = events_path
        self.events = []
        self.lock = threading.Lock()
        self.cancel = threading.Event()
        self.done = threading.Event()
        self.thread = None

    def add(self, step, status, message, data):
        with self.lock:
            entry = {"seq": len(self.events) + 1, "ts": _now(), "step": step, "status": status,
                     "message": message, "data": data or {}}
            self.events.append(entry)
        with open(self.events_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, default=str) + "\n")
        if status == "log":
            with open(self.log_path, "a", encoding="utf-8") as handle:
                level = (data or {}).get("level", "info").upper()
                handle.write(f"{entry['ts']} {level:<7} [{step or '-'}] {message}\n")
        return entry

    def since(self, seq):
        with self.lock:
            return self.events[seq:]


def read_events_file(path, after=0):
    path = resolve_project_path(path)
    if not path.exists():
        return []
    events = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("seq", 0) > after:
                events.append(entry)
    return events


def step_summary(events):
    """Collapse events into one state per step for the stepper."""
    steps = {name: {"step": name, "label": STEP_LABELS[name], "status": "pending", "message": "",
                    "started_at": None, "finished_at": None, "data": {}} for name in STEPS}
    for entry in events:
        name = entry.get("step")
        if name not in steps or entry["status"] == "log":
            continue
        current = steps[name]
        status = entry["status"]
        if status == "started":
            current.update(status="running", started_at=entry["ts"], message=entry["message"])
        elif status == "progress":
            current["status"] = "running"
            current["message"] = entry["message"]
            current["started_at"] = current["started_at"] or entry["ts"]
        else:
            current.update(status=status, finished_at=entry["ts"], message=entry["message"])
            current["started_at"] = current["started_at"] or entry["ts"]
        current["data"] = {**current["data"], **(entry.get("data") or {})}
    return list(steps.values())


def row_to_run(row, events=None):
    run = dict(row)
    for key in ("options", "summary"):
        try:
            run[key] = json.loads(run.get(key) or "{}")
        except ValueError:
            run[key] = {}
    if events is not None:
        run["steps"] = step_summary(events)
    started, finished = run.get("started_at"), run.get("finished_at")
    if started and finished:
        run["duration_seconds"] = (
            datetime.fromisoformat(finished) - datetime.fromisoformat(started)
        ).total_seconds()
    else:
        run["duration_seconds"] = None
    return run


def events_path_for(run_id):
    return RUNS_DIR / f"run_{run_id}.events.jsonl"


def mark_interrupted_runs():
    init_db(quiet=True)
    with transaction() as conn:
        conn.execute(
            "UPDATE runs SET status = 'failed', finished_at = ?, error = ? WHERE status = 'running'",
            (_now(), "The server stopped while this run was in progress."),
        )


class RunManager:
    """Owns the single active run. One instance lives on app.state."""

    def __init__(self, pipeline=None):
        self._lock = threading.Lock()
        self.active = None
        self.recent = {}
        self._pipeline = pipeline

    def pipeline(self):
        if self._pipeline is None:
            from main import run_agent

            return run_agent
        return self._pipeline

    def start(self, options):
        with self._lock:
            if self.active and not self.active.done.is_set():
                raise RunConflict(self.active.id)
            init_db(quiet=True)
            RUNS_DIR.mkdir(parents=True, exist_ok=True)
            with transaction() as conn:
                cursor = conn.execute(
                    "INSERT INTO runs (started_at, status, options) VALUES (?, 'running', ?)",
                    (_now(), json.dumps(options)),
                )
                run_id = cursor.lastrowid
                log_path = RUNS_DIR / f"run_{run_id}.log"
                conn.execute("UPDATE runs SET log_path = ? WHERE id = ?", (relative_to_project(log_path), run_id))
            log_path.write_text("", encoding="utf-8")
            state = RunState(run_id, log_path, events_path_for(run_id))
            state.events_path.write_text("", encoding="utf-8")
            state.thread = threading.Thread(target=self._execute, args=(state, options), name=f"run-{run_id}", daemon=True)
            self.active = state
            self.recent[run_id] = state
            state.thread.start()
            return run_id

    def _execute(self, state, options):
        status, error, summary = "succeeded", "", {}
        try:
            summary = self.pipeline()(on_event=state.add, options=options, cancel_event=state.cancel,
                                      run_id=state.id, interactive=False) or {}
        except RunCancelled:
            status, error = "cancelled", "Cancelled by you."
            state.add(None, "cancelled", "Run cancelled. Work finished before the cancel was kept.", {})
        except SystemExit as exit_error:
            status, error = "failed", str(exit_error)
            state.add(None, "failed", str(exit_error), {})
        except Exception as exc:
            status, error = "failed", f"{type(exc).__name__}: {exc}"
            state.add(None, "failed", error, {"traceback": traceback.format_exc()})
        finally:
            with transaction() as conn:
                conn.execute(
                    """UPDATE runs SET status = ?, finished_at = ?, error = ?, discovered = ?, "new" = ?,
                    filtered = ?, tailored = ?, failed = ?, summary = ? WHERE id = ?""",
                    (status, _now(), error, summary.get("discovered", 0), summary.get("new", 0),
                     summary.get("filtered", 0), summary.get("tailored", 0), summary.get("failed", 0),
                     json.dumps(summary, default=str), state.id),
                )
            state.add(None, "finished", f"Run {status}.", {"run_status": status})
            state.done.set()

    def cancel(self, run_id):
        state = self.recent.get(run_id)
        if not state or state.done.is_set():
            return False
        state.cancel.set()
        state.add(None, "cancelling", "Cancelling after the current step or job finishes.", {})
        return True

    def active_run_id(self):
        state = self.active
        return state.id if state and not state.done.is_set() else None

    def events(self, run_id, after=0):
        state = self.recent.get(run_id)
        if state:
            return state.since(after), state.done.is_set()
        return read_events_file(events_path_for(run_id), after), True

    def wait(self, run_id, timeout=None):
        state = self.recent.get(run_id)
        if state:
            state.done.wait(timeout)
