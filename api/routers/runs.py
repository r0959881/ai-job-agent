"""Start, watch (SSE), cancel and review pipeline runs."""
import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from api import db
from api.services.runs import RunConflict, events_path_for, read_events_file, row_to_run
from config import resolve_project_path

router = APIRouter(prefix="/api/runs", tags=["runs"])
SOURCES = {"adzuna", "arbeitnow", "gmail"}


class RunOptions(BaseModel):
    sources: list[str] | None = None
    time_window_hours: int | None = Field(None, ge=1, le=24 * 60)
    max_tailor: int | None = Field(None, ge=0, le=1000)
    dry_run: bool = False

    @field_validator("sources")
    @classmethod
    def known_sources(cls, value):
        if value is None:
            return value
        unknown = set(value) - SOURCES
        if unknown:
            raise ValueError(f"Unknown source(s): {', '.join(sorted(unknown))}")
        if not value:
            raise ValueError("Pick at least one source")
        return value


def manager(request: Request):
    return request.app.state.runs


def _fetch_runs(limit):
    return db.all_rows("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,))


def _fetch_run(run_id):
    row = db.one_row("SELECT * FROM runs WHERE id = ?", (run_id,))
    docs = db.all_rows(
        """SELECT d.*, j.title AS job_title, j.company AS job_company FROM documents d
        LEFT JOIN jobs j ON j.id = d.job_id WHERE d.run_id = ? ORDER BY d.id""",
        (run_id,),
    )
    return row, docs


@router.post("", status_code=201)
def start_run(body: RunOptions, request: Request):
    try:
        run_id = manager(request).start(body.model_dump(exclude_none=True))
    except RunConflict as exc:
        raise HTTPException(409, {"message": str(exc), "run_id": exc.run_id}) from exc
    return {"id": run_id}


@router.get("")
def list_runs(request: Request, limit: int = 50):
    runs = [row_to_run(row) for row in _fetch_runs(max(1, min(limit, 500)))]
    active_id = manager(request).active_run_id()
    active = None
    if active_id:
        events, _done = manager(request).events(active_id)
        row, _docs = _fetch_run(active_id)
        active = row_to_run(row, events) if row else None
    return {"items": runs, "active_id": active_id, "active": active}


@router.get("/{run_id}")
def get_run(run_id: int, request: Request):
    row, docs = _fetch_run(run_id)
    if not row:
        raise HTTPException(404, f"Run {run_id} does not exist.")
    events, _done = manager(request).events(run_id)
    from api.services.documents import document_row

    run = row_to_run(row, events)
    run["documents"] = [document_row(doc) for doc in docs]
    return run


@router.get("/{run_id}/log", response_class=PlainTextResponse)
def get_log(run_id: int):
    row, _docs = _fetch_run(run_id)
    if not row:
        raise HTTPException(404, f"Run {run_id} does not exist.")
    path = resolve_project_path(row.get("log_path") or "")
    if not row.get("log_path") or not path.exists():
        return PlainTextResponse("No log was written for this run.")
    return PlainTextResponse(path.read_text(encoding="utf-8", errors="replace"))


@router.post("/{run_id}/cancel")
def cancel_run(run_id: int, request: Request):
    if not manager(request).cancel(run_id):
        raise HTTPException(409, "This run is not running, so there is nothing to cancel.")
    return {"cancelling": True}


@router.get("/{run_id}/events")
async def run_events(run_id: int, request: Request):
    """Server-Sent Events: replays past events, then streams new ones until the run ends."""
    row, _docs = _fetch_run(run_id)
    if not row:
        raise HTTPException(404, f"Run {run_id} does not exist.")
    try:
        after = int(request.headers.get("last-event-id") or request.query_params.get("after") or 0)
    except ValueError:
        after = 0
    runs = manager(request)

    async def stream():
        seq = after
        idle = 0
        yield "retry: 2000\n\n"
        while True:
            if runs.recent.get(run_id):
                events, done = runs.events(run_id, seq)
            else:
                events, done = read_events_file(events_path_for(run_id), seq), True
            for entry in events:
                seq = entry["seq"]
                yield f"id: {seq}\ndata: {json.dumps(entry, default=str)}\n\n"
            if done and not events:
                yield "event: end\ndata: {}\n\n"
                return
            if await request.is_disconnected():
                return
            idle = 0 if events else idle + 1
            if idle and idle % 50 == 0:
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.25)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
