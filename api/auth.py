"""Sign in with Google or LinkedIn (OpenID Connect), sessions and request protection.

Both providers only share the basic profile: name, email and photo. LinkedIn's
API does not give third-party apps your work history, so the resume itself is
still filled from a CV upload or the LinkedIn data export.

Sessions are signed cookies (SameSite=Lax, HttpOnly). Every write request must
also send the session's CSRF token in X-CSRF-Token, which other sites cannot
read, so they cannot act for a signed-in user.
"""
import base64
import hashlib
import secrets
from typing import Any
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

import user_scope
from api import server_config, store

CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
PUBLIC_PATHS = {"/api/health", "/api/session"}
TIMEOUT = 20

PROVIDERS: dict[str, dict[str, Any]] = {
    "google": {
        "label": "Google",
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "userinfo": "https://openidconnect.googleapis.com/v1/userinfo",
        "scope": "openid email profile",
        "pkce": True,
        "extra": {"prompt": "select_account"},
    },
    "linkedin": {
        "label": "LinkedIn",
        "authorize": "https://www.linkedin.com/oauth/v2/authorization",
        "token": "https://www.linkedin.com/oauth/v2/accessToken",
        "userinfo": "https://api.linkedin.com/v2/userinfo",
        "scope": "openid profile email",
        "pkce": False,
        "extra": {},
    },
}

router = APIRouter(prefix="/api/auth", tags=["auth"])


class AuthError(Exception):
    pass


# ------------------------------------------------------------------------------ middleware

class AuthMiddleware:
    """Checks the Host header, requires a signed-in user for /api/*, checks CSRF on writes,
    and runs the request inside that user's scope."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request = Request(scope)
        host = (request.headers.get("host") or "").split(":")[0].lower()
        if host not in server_config.allowed_hosts():
            return await JSONResponse({"detail": "Unknown host."}, status_code=400)(scope, receive, send)
        path = scope["path"]
        if not path.startswith("/api/") or path in PUBLIC_PATHS or path.startswith("/api/auth/"):
            if request.method not in SAFE_METHODS and path.startswith("/api/auth/") and not _csrf_ok(request):
                return await _csrf_error()(scope, receive, send)
            return await self.app(scope, receive, send)
        session = scope.get("session") or {}
        user_id = session.get("user_id")
        if not user_id or store.get_user(user_id) is None:
            session.pop("user_id", None)  # keep the CSRF token, so the sign-in that follows still works
            return await JSONResponse({"detail": "Please sign in.", "code": "signed_out"},
                                      status_code=401)(scope, receive, send)
        if request.method not in SAFE_METHODS and not _csrf_ok(request):
            return await _csrf_error()(scope, receive, send)
        if uses_project_files(session):
            return await self.app(scope, receive, send)  # the local account: project files, no user scope
        with user_scope.use(user_id):
            await self.app(scope, receive, send)


def uses_project_files(session):
    """The automatic local account works on resume_data.yaml, agent_settings.yaml, .env and output/."""
    return bool(session.get("project_files")) and server_config.local_mode()


def local_sign_in(request: Request):
    """Sign in as the local account (local mode only)."""
    from config import load_resume_file

    name = ((load_resume_file() or {}).get("personal_info") or {}).get("full_name") or "Local user"
    owner = server_config.project_owner_email()
    if owner:  # the same account as the developer sign-in (or Google) with that email
        user, _created = store.sign_in("dev", owner, owner, name)
    else:
        user, _created = store.sign_in(server_config.LOCAL_PROVIDER, "local", None, name)
    request.session.clear()
    request.session.update(user_id=user["id"], csrf=secrets.token_urlsafe(32), project_files=True)
    return user


def _csrf_ok(request):
    expected = (request.scope.get("session") or {}).get("csrf", "")
    supplied = request.headers.get(CSRF_HEADER, "")
    return bool(expected) and secrets.compare_digest(supplied, expected)


def _csrf_error():
    return JSONResponse({"detail": "Your session expired. Reload the page and try again.", "code": "csrf"},
                        status_code=403)


def csrf_token(request: Request):
    token = request.session.get("csrf")
    if not token:
        token = request.session["csrf"] = secrets.token_urlsafe(32)
    return token


# --------------------------------------------------------------------------------- helpers

def public_user(user):
    return {"id": user["id"], "email": user.get("email") or "", "name": user.get("name") or "",
            "picture": user.get("picture") or "", "providers": store.providers_for(user["id"])}


def configured_providers():
    items = [{"id": key, "label": spec["label"]} for key, spec in PROVIDERS.items() if server_config.oauth_client(key)]
    if server_config.local_mode():
        owner = server_config.project_owner_email()
        items.append({"id": "local", "label": f"Local account ({owner or 'this PC'}'s project files)"})
    if server_config.dev_login_enabled():
        items.append({"id": "dev", "label": "Developer sign-in"})
    return items


def redirect_uri(request: Request, provider):
    base = server_config.public_url() or str(request.base_url).rstrip("/")
    return f"{base}/api/auth/{provider}/callback"


def safe_next(target):
    """Only same-site paths, so the sign-in link cannot be used to bounce users to another site."""
    target = target or "/"
    if not target.startswith("/") or target.startswith("//") or "\\" in target:
        return "/"
    return target


def _pkce_pair():
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode().rstrip("=")
    return verifier, challenge


def finish_sign_in(request: Request, provider, subject, email, name, picture):
    """Create or update the user, start a fresh session and seed a new user's resume."""
    if not server_config.email_allowed(email):
        raise AuthError("This app is invite-only and your email address is not on the list.")
    user, created = store.sign_in(provider, subject, email, name, picture)
    request.session.clear()
    request.session["user_id"] = user["id"]
    request.session["csrf"] = secrets.token_urlsafe(32)
    owner = server_config.project_owner_email()
    if server_config.local_mode() and owner and (user.get("email") or "").lower() == owner:
        request.session["project_files"] = True  # the owner of this PC's project files
        return user
    if created:
        seed_resume(user)
    return user


def seed_resume(user):
    """Start a new user's resume with the name and email from their sign-in."""
    from api.services import resume_store

    with user_scope.use(user["id"]):
        if resume_store.read_text().strip():
            return
        try:
            resume_store.save({"personal_info": {"full_name": user.get("name") or "", "email": user.get("email") or ""}},
                              label="import")
        except resume_store.ResumeInvalid:
            pass  # an unusual name or email must not block sign-in; onboarding asks again


def exchange_code(provider, code, redirect, verifier=None):
    """Code -> access token -> profile. Returns (subject, email, name, picture)."""
    spec = PROVIDERS[provider]
    client = server_config.oauth_client(provider)
    if not client:
        raise AuthError(f"Sign-in with {spec['label']} is not set up on this server.")
    client_id, client_secret = client
    form = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect,
            "client_id": client_id, "client_secret": client_secret}
    if verifier:
        form["code_verifier"] = verifier
    try:
        token_response = requests.post(spec["token"], data=form, headers={"Accept": "application/json"},
                                       timeout=TIMEOUT)
        token_response.raise_for_status()
        access_token = token_response.json().get("access_token")
        if not access_token:
            raise AuthError(f"{spec['label']} did not return an access token.")
        info_response = requests.get(spec["userinfo"], headers={"Authorization": f"Bearer {access_token}"},
                                     timeout=TIMEOUT)
        info_response.raise_for_status()
        info = info_response.json()
    except requests.RequestException as error:
        raise AuthError(f"{spec['label']} sign-in failed: {error}") from error
    except ValueError as error:
        raise AuthError(f"{spec['label']} sent an unreadable answer.") from error
    subject = str(info.get("sub") or "")
    if not subject:
        raise AuthError(f"{spec['label']} did not identify the account.")
    verified = info.get("email_verified")
    email = info.get("email") if verified in (True, "true", None) else None
    name = info.get("name") or " ".join(filter(None, [info.get("given_name"), info.get("family_name")]))
    return subject, email, name, info.get("picture") or ""


# ---------------------------------------------------------------------------------- routes

@router.get("/providers")
def providers():
    return {"providers": configured_providers()}


@router.get("/{provider}/login")
def login(provider: str, request: Request, next: str = "/"):
    if provider not in PROVIDERS:
        raise HTTPException(404, "Unknown sign-in provider.")
    client = server_config.oauth_client(provider)
    if not client:
        return RedirectResponse(f"/login?error={PROVIDERS[provider]['label']}+sign-in+is+not+set+up", status_code=302)
    spec = PROVIDERS[provider]
    state = secrets.token_urlsafe(24)
    pending = {"state": state, "provider": provider, "next": safe_next(next)}
    params = {"response_type": "code", "client_id": client[0], "redirect_uri": redirect_uri(request, provider),
              "scope": spec["scope"], "state": state, **spec["extra"]}
    if spec["pkce"]:
        verifier, challenge = _pkce_pair()
        pending["verifier"] = verifier
        params.update(code_challenge=challenge, code_challenge_method="S256")
    request.session["oauth"] = pending
    return RedirectResponse(f"{spec['authorize']}?{urlencode(params)}", status_code=302)


@router.get("/{provider}/callback")
def callback(provider: str, request: Request, code: str = "", state: str = "", error: str = ""):
    pending = request.session.pop("oauth", None) or {}
    label = PROVIDERS.get(provider, {}).get("label", provider)

    def fail(reason):
        return RedirectResponse(f"/login?{urlencode({'error': reason})}", status_code=302)

    if error:
        return fail("You cancelled the sign-in." if error in {"access_denied", "user_cancelled_login"}
                    else f"{label} returned “{error}”.")
    if provider not in PROVIDERS or pending.get("provider") != provider or not state \
            or not secrets.compare_digest(state, pending.get("state", "")):
        return fail("The sign-in expired or was started in another tab. Please try again.")
    try:
        subject, email, name, picture = exchange_code(provider, code, redirect_uri(request, provider),
                                                      pending.get("verifier"))
        finish_sign_in(request, provider, subject, email, name, picture)
    except AuthError as exc:
        return fail(str(exc))
    return RedirectResponse(pending.get("next") or "/", status_code=302)


class DevLogin(BaseModel):
    email: str
    name: str = ""


@router.post("/dev/login")
def dev_login(body: DevLogin, request: Request):
    if not server_config.dev_login_enabled():
        raise HTTPException(404, "Developer sign-in is turned off.")
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(422, "Enter an email address.")
    try:
        user = finish_sign_in(request, "dev", email, email, body.name.strip() or email.split("@")[0], "")
    except AuthError as exc:
        raise HTTPException(403, str(exc)) from exc
    return {"user": public_user(user), "csrf": request.session["csrf"]}


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    if server_config.local_mode():
        request.session["signed_out"] = True  # do not sign straight back in as the local account
    return {"signed_out": True}


@router.post("/local/login")
def local_login(request: Request):
    """Back to the local account after trying another one with the developer sign-in."""
    if not server_config.local_mode():
        raise HTTPException(404, "The local account only exists when the app runs on your own PC.")
    return {"user": public_user(local_sign_in(request)), "csrf": request.session["csrf"]}


def session_info(request: Request):
    """The signed-in user (or None), the CSRF token and the sign-in options, for the web app's first request."""
    user_id = request.session.get("user_id")
    user = store.get_user(user_id) if user_id else None
    if user_id and user is None:
        request.session.pop("user_id", None)
    if user is None and server_config.local_mode() and not request.session.get("signed_out"):
        user = local_sign_in(request)
    return {"user": public_user(user) if user else None, "csrf": csrf_token(request),
            "providers": configured_providers(), "project_files": uses_project_files(request.session)}
