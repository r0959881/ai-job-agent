"""FastAPI application factory.

Locally: `python serve.py`. On cPanel: passenger_wsgi.py wraps create_app() for Passenger.
"""
import importlib
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.middleware.sessions import SessionMiddleware

from api import server_config, store
from api.auth import AuthMiddleware, session_info
from config import WEB_DIST

logger = logging.getLogger("ai_job_agent.api")
VERSION = "2.0.0"
SESSION_DAYS = 30

ROUTER_MODULES = [
    "api.auth",
    "api.routers.account",
    "api.routers.resume",
    "api.routers.settings",
    "api.routers.integrations",
    "api.routers.search",
    "api.routers.documents",
    "api.routers.local",
]

SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"same-origin"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
]


class SecurityHeaders:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                names = {name for name, _ in message.get("headers", [])}
                message.setdefault("headers", [])
                message["headers"] += [header for header in SECURITY_HEADERS if header[0] not in names]
            await send(message)

        await self.app(scope, receive, send_with_headers)


def create_app():
    app = FastAPI(title="AI Job Agent", version=VERSION, docs_url=None, redoc_url=None, openapi_url=None)
    # Added inner to outer: the session must be decoded before AuthMiddleware reads it.
    app.add_middleware(AuthMiddleware)
    app.add_middleware(SessionMiddleware, secret_key=server_config.secret_key(), session_cookie="aja_session",
                       max_age=SESSION_DAYS * 24 * 3600, same_site="lax", https_only=server_config.cookie_secure())
    app.add_middleware(SecurityHeaders)
    store.init_schema()
    from api import dev_fakes

    app.state.fake_sources = dev_fakes.install()
    if app.state.fake_sources:
        logger.warning("AI_JOB_AGENT_FAKE_SOURCES=1: using offline fake job sources and Groq.")

    @app.get("/api/health")
    def health():
        try:
            store.get_user(0)
            database = True
        except Exception:
            logger.exception("Database check failed")
            database = False
        return {"status": "ok" if database else "degraded", "version": VERSION, "database": database,
                "fake_sources": app.state.fake_sources}

    @app.get("/api/session")
    def session(request: Request):
        """The signed-in user, the CSRF token for write requests and the sign-in options."""
        return session_info(request)

    for module_name in ROUTER_MODULES:
        app.include_router(importlib.import_module(module_name).router)

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
