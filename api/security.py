"""Single-user protection: localhost-only hosts and a per-install token for writes.

The token lives in the gitignored .ui_token file and is sent by the web app in
the X-UI-Token header. Other browser tabs cannot read it (same-origin policy),
so they cannot forge mutating requests. The Host check blocks DNS rebinding.
"""
import os
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from config import UI_TOKEN_PATH, atomic_write_text

TOKEN_HEADER = "X-UI-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
ALLOWED_HOSTS = {"127.0.0.1", "localhost"}


def get_ui_token():
    try:
        token = UI_TOKEN_PATH.read_text(encoding="utf-8").strip()
        if token:
            return token
    except OSError:
        pass
    token = secrets.token_urlsafe(32)
    atomic_write_text(UI_TOKEN_PATH, token)
    return token


def _host_name(host_header):
    host = (host_header or "").strip().lower()
    if host.startswith("["):
        return host.split("]")[0] + "]"
    return host.split(":")[0]


class LocalOnlyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, token=None, extra_origins=()):
        super().__init__(app)
        self.token = token or get_ui_token()
        self.extra_origins = set(extra_origins)

    def _origin_ok(self, request):
        origin = request.headers.get("origin")
        if not origin:
            return True
        host = request.headers.get("host", "")
        return origin in {f"http://{host}", f"https://{host}"} | self.extra_origins

    async def dispatch(self, request, call_next):
        if _host_name(request.headers.get("host")) not in ALLOWED_HOSTS and not os.environ.get("AI_JOB_AGENT_ANY_HOST"):
            return JSONResponse({"detail": "This server only answers on localhost."}, status_code=400)
        if request.method not in SAFE_METHODS and request.url.path.startswith("/api/"):
            if not self._origin_ok(request):
                return JSONResponse({"detail": "Cross-origin requests are not allowed."}, status_code=403)
            supplied = request.headers.get(TOKEN_HEADER, "")
            if not secrets.compare_digest(supplied, self.token):
                return JSONResponse(
                    {"detail": "Missing or wrong UI token. Reload the page to get a fresh one."},
                    status_code=403,
                )
        return await call_next(request)
