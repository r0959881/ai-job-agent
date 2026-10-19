"""Integration health, connection tests and the Gmail OAuth web flow."""
import os
import smtplib
from email.message import EmailMessage
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

import agent_settings
from api.integrations import gmail
from api.services import integrations, secrets

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


def pending(request: Request):
    store = getattr(request.app.state, "gmail_pending", None)
    if store is None:
        store = request.app.state.gmail_pending = gmail.PendingStates()
    return store


def redirect_uri(request: Request):
    port = request.url.port
    host = f"127.0.0.1:{port}" if port else "127.0.0.1"
    return f"http://{host}{gmail.REDIRECT_PATH}"


def ui_url(path, **params):
    origin = os.environ.get("AI_JOB_AGENT_UI_ORIGIN", "")
    joiner = "&" if "?" in path else "?"
    return f"{origin}{path}" + (f"{joiner}{urlencode(params)}" if params else "")


@router.get("/status")
def status():
    return integrations.status()


@router.get("/gmail/connect")
def gmail_connect(request: Request, return_to: str = "/settings/integrations"):
    """302 to Google's consent screen. The state and PKCE verifier are checked on the way back."""
    try:
        url = gmail.authorization_url(pending(request), redirect_uri(request), return_to)
    except gmail.GmailOAuthError as exc:
        return RedirectResponse(ui_url("/settings/integrations", gmail="error", reason=str(exc)), status_code=302)
    return RedirectResponse(url, status_code=302)


@router.get("/gmail/callback")
def gmail_callback(request: Request, state: str = "", code: str = "", error: str = ""):
    if error:
        reason = "You cancelled the Google sign-in." if error == "access_denied" else f"Google returned “{error}”."
        return RedirectResponse(ui_url("/settings/integrations", gmail="denied", reason=reason), status_code=302)
    if not code:
        return RedirectResponse(ui_url("/settings/integrations", gmail="error", reason="Google sent no code."),
                                status_code=302)
    try:
        return_to = gmail.complete(pending(request), state, code)
    except gmail.GmailOAuthError as exc:
        return RedirectResponse(ui_url("/settings/integrations", gmail="error", reason=str(exc)), status_code=302)
    return RedirectResponse(ui_url(return_to, gmail="connected"), status_code=302)


@router.get("/gmail/status")
def gmail_status(request: Request):
    return {**gmail.status(), "redirect_uri": redirect_uri(request)}


@router.post("/gmail/test")
def gmail_test():
    from gmail_parser import GmailAuthRequired

    try:
        return gmail.test_connection()
    except GmailAuthRequired as exc:
        raise HTTPException(409, {"message": exc.reason, "state": exc.status}) from exc
    except Exception as exc:
        raise HTTPException(502, f"Gmail did not answer: {exc}") from exc


@router.post("/gmail/disconnect")
def gmail_disconnect():
    return gmail.disconnect()


@router.post("/{name}/test")
def test_integration(name: str):
    if name == "groq":
        from tailor import GroqConfigError, describe_error, get_client

        try:
            models = get_client().models.list()
            count = len(getattr(models, "data", []) or [])
            return {"ok": True, "message": f"Groq answered ({count} models available)."}
        except GroqConfigError as exc:
            return {"ok": False, "message": str(exc).removeprefix("❌ ")}
        except Exception as exc:
            return {"ok": False, "message": f"Groq test failed: {describe_error(exc)}."}
    if name == "adzuna":
        app_id, app_key = secrets.get("ADZUNA_APP_ID"), secrets.get("ADZUNA_APP_KEY")
        if not app_id or not app_key:
            return {"ok": False, "message": "Add both the Adzuna app ID and key first."}
        country = agent_settings.get("adzuna")["country"]
        try:
            response = requests.get(f"https://api.adzuna.com/v1/api/jobs/{country}/search/1",
                                    params={"app_id": app_id, "app_key": app_key, "results_per_page": 1,
                                            "what": "data"}, timeout=20)
            if response.status_code in {401, 403}:
                return {"ok": False, "message": "Adzuna rejected the app ID or key."}
            response.raise_for_status()
            total = response.json().get("count")
            return {"ok": True, "message": f"Adzuna answered{f' ({total} “data” jobs listed)' if total else ''}."}
        except (requests.RequestException, ValueError) as exc:
            return {"ok": False, "message": f"Adzuna could not be reached: {exc}"}
    if name == "smtp":
        sender, password, receiver = (secrets.get("ALERT_EMAIL_FROM"), secrets.get("ALERT_EMAIL_PASS"),
                                      secrets.get("ALERT_EMAIL_TO"))
        if not (sender and password and receiver):
            return {"ok": False, "message": "Add the Gmail address, app password and recipient first."}
        message = EmailMessage()
        message["Subject"] = "AI Job Agent: test alert"
        message["From"], message["To"] = sender, receiver
        message.set_content("This is a test from the AI Job Agent web UI. Email alerts are working.")
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as server:
                server.login(sender, password)
                server.send_message(message)
            return {"ok": True, "message": f"Test email sent to {secrets.mask(receiver)}."}
        except smtplib.SMTPAuthenticationError:
            return {"ok": False, "message": "Gmail rejected the login. Use an app password, not your normal password."}
        except (smtplib.SMTPException, OSError) as exc:
            return {"ok": False, "message": f"The test email failed: {exc}"}
    raise HTTPException(404, f"Unknown integration “{name}”.")
