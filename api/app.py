"""FastAPI application factory. Start it with `python serve.py`."""
import contextlib
import importlib
import logging
import threading

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

import agent_settings
from api.paths import UnsafePath
from api.security import LocalOnlyMiddleware, get_ui_token
from config import DB_PATH, RESUME_PATH, SETTINGS_PATH, WEB_DIST
from database import init_db

logger = logging.getLogger("ai_job_agent.api")
VERSION = "1.0.0"

# Routers are added phase by phase; each module exposes `router`.
ROUTER_MODULES = [
    "api.routers.resume",
    "api.routers.settings",
    "api.routers.integrations",
    "api.routers.runs",
    "api.routers.jobs",
    "api.routers.documents",
    "api.routers.stats",
    "api.routers.data",
]


def _startup():
    init_db(quiet=True)
    if not SETTINGS_PATH.exists():
        from generate_cover_letter import ROLE_LETTERS

        agent_settings.seed(cover_letters=ROLE_LETTERS)
    from api.services.runs import mark_interrupted_runs

    mark_interrupted_runs()

    def backfill():
        try:
            from api.services.documents import backfill_documents

            logger.info("Document backfill: %s", backfill_documents())
        except Exception:  # Backfill is best-effort and must not stop the server.
            logger.exception("Document backfill failed")

    threading.Thread(target=backfill, name="document-backfill", daemon=True).start()


def create_app(dev_origins=(), run_startup=True, run_manager=None):
    @contextlib.asynccontextmanager
    async def lifespan(_app):
        if run_startup:
            _startup()
        yield

    app = FastAPI(title="AI Job Agent", version=VERSION, docs_url="/api/docs",
                  openapi_url="/api/openapi.json", lifespan=lifespan)
    app.add_middleware(LocalOnlyMiddleware, token=get_ui_token(), extra_origins=dev_origins)
    from api.services.runs import RunManager

    app.state.runs = run_manager or RunManager()
    from api import dev_fakes

    app.state.fake_sources = dev_fakes.install()
    if app.state.fake_sources:
        logger.warning("AI_JOB_AGENT_FAKE_SOURCES=1: using offline fake job sources, Groq and Gmail.")

    @app.exception_handler(UnsafePath)
    async def unsafe_path(_request: Request, error: UnsafePath):
        return JSONResponse({"detail": str(error)}, status_code=403)

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "version": VERSION,
            "database": DB_PATH.exists(),
            "resume": RESUME_PATH.exists(),
            "fake_sources": app.state.fake_sources,
        }

    @app.get("/api/session")
    def session():
        """The web app reads its write token here. Other origins cannot read this response."""
        return {"token": get_ui_token()}

    for module_name in ROUTER_MODULES:
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as error:
            if error.name == module_name:
                continue
            raise
        app.include_router(module.router)

    @app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    def api_not_found(rest: str):
        raise HTTPException(404, f"No API endpoint at /api/{rest}.")

    if WEB_DIST.exists():
        index = WEB_DIST / "index.html"

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            candidate = (WEB_DIST / path).resolve()
            if path and candidate.is_file() and WEB_DIST.resolve() in candidate.parents:
                headers = {"Cache-Control": "public, max-age=31536000, immutable"} if path.startswith("assets/") else {}
                return FileResponse(candidate, headers=headers)
            return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return app
