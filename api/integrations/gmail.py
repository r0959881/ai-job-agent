"""Gmail sign-in from the browser (OAuth web flow) and connection health.

The CLI keeps InstalledAppFlow.run_local_server(); the server never opens a
browser itself. A Desktop ("installed") OAuth client accepts loopback redirects
on any port, so nothing has to be registered in Google Cloud Console. A "web"
client needs REDIRECT_PATH registered for http://127.0.0.1:<port>.
"""
import json
import os
import secrets
import threading
import time
from datetime import UTC, datetime

import requests
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from config import CREDENTIALS_PATH, TOKEN_PATH
from gmail_parser import SCOPES, read_gmail_state, save_token, update_gmail_state

REDIRECT_PATH = "/api/integrations/gmail/callback"
STATE_TTL = 600
REVOKE_URL = "https://oauth2.googleapis.com/revoke"

# Google may return scopes in a different order or add openid; that is fine for a read-only token.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")


class GmailOAuthError(Exception):
    pass


def now():
    return datetime.now(UTC).isoformat()


def client_type():
    try:
        data = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return next((kind for kind in ("installed", "web") if kind in data), None)


class PendingStates:
    """state -> (code_verifier, redirect_uri, created, return_to). One instance lives on app.state."""

    def __init__(self):
        self._lock = threading.Lock()
        self._items = {}

    def add(self, state, verifier, redirect_uri, return_to="/settings/integrations"):
        with self._lock:
            cutoff = time.time() - STATE_TTL
            self._items = {k: v for k, v in self._items.items() if v[2] > cutoff}
            self._items[state] = (verifier, redirect_uri, time.time(), return_to)

    def pop(self, state):
        with self._lock:
            item = self._items.pop(state or "", None)
        if not item or item[2] < time.time() - STATE_TTL:
            return None
        return item


def _flow(redirect_uri, state=None):
    if not CREDENTIALS_PATH.exists():
        raise GmailOAuthError("credentials.json is missing. Download it from Google Cloud Console first.")
    return Flow.from_client_secrets_file(str(CREDENTIALS_PATH), scopes=SCOPES, redirect_uri=redirect_uri, state=state)


def safe_return_path(path):
    """Only same-app paths like /onboarding?step=connect; never another site."""
    if path and path.startswith("/") and not path.startswith("//") and "\\" not in path and ":" not in path.split("?")[0]:
        return path
    return "/settings/integrations"


def authorization_url(pending, redirect_uri, return_to=None):
    """Build Google's consent URL with a random state and PKCE; remember them for the callback."""
    flow = _flow(redirect_uri)
    flow.code_verifier = secrets.token_urlsafe(64)
    state = secrets.token_urlsafe(24)
    url, _ = flow.authorization_url(state=state, access_type="offline", prompt="consent",
                                    include_granted_scopes="true")
    pending.add(state, flow.code_verifier, redirect_uri, safe_return_path(return_to))
    return url


def complete(pending, state, code):
    """Validate the state, exchange the code (with the PKCE verifier) and save token.json atomically."""
    item = pending.pop(state)
    if not item:
        raise GmailOAuthError("The sign-in link expired or did not come from this app. Start again from Settings.")
    verifier, redirect_uri, _created, return_to = item
    flow = _flow(redirect_uri, state=state)
    flow.code_verifier = verifier
    try:
        flow.fetch_token(code=code)
    except Exception as exc:
        raise GmailOAuthError(f"Google did not accept the sign-in: {exc}") from exc
    creds = flow.credentials
    if not creds.refresh_token:
        raise GmailOAuthError("Google did not return a refresh token. Remove the app's access in your Google "
                              "account settings and connect again.")
    save_token(creds)
    update_gmail_state(status="connected", reason="", connected_at=now(), last_refresh=now())
    try:
        email = profile_email(creds)
        update_gmail_state(email=email)
    except Exception:  # The profile lookup is a nicety; the connection itself worked.
        pass
    return return_to


def load_credentials():
    if not TOKEN_PATH.exists():
        return None
    try:
        return Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    except (ValueError, KeyError):
        return None


def profile_email(creds):
    from googleapiclient.discovery import build

    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    return service.users().getProfile(userId="me").execute().get("emailAddress")


def status(check_refresh=True):
    """Connection state without ever opening a browser. Refreshes an expired token when asked."""
    state = read_gmail_state()
    creds = load_credentials()
    info = {
        "state": "not_connected", "connected": False, "email": state.get("email"), "scopes": [], "read_only": True,
        "token_expiry": None, "last_refresh": state.get("last_refresh"), "last_fetch": state.get("last_fetch"),
        "last_message_count": state.get("last_message_count"), "reason": "",
        "credentials_present": CREDENTIALS_PATH.exists(), "client_type": client_type(),
    }
    if not creds:
        if TOKEN_PATH.exists():
            info.update(state="error", reason="token.json is unreadable. Disconnect and connect again.")
        return info
    info["scopes"] = list(creds.scopes or SCOPES)
    info["read_only"] = all(scope.endswith("readonly") for scope in info["scopes"])
    if state.get("status") == "reauth_required":
        return {**info, "state": "reauth_required", "reason": state.get("reason") or "Google revoked the access."}
    if check_refresh and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            save_token(creds)
            update_gmail_state(last_refresh=now(), status="connected", reason="")
            info["last_refresh"] = now()
        except RefreshError as exc:
            update_gmail_state(status="reauth_required", reason=str(exc))
            return {**info, "state": "reauth_required", "reason": _friendly_refresh_error(exc)}
        except Exception as exc:
            return {**info, "state": "error", "reason": f"Could not reach Google to refresh the token: {exc}"}
    info.update(state="connected", connected=True,
                token_expiry=creds.expiry.replace(tzinfo=UTC).isoformat() if creds.expiry else None)
    return info


def _friendly_refresh_error(exc):
    text = str(exc)
    if "invalid_grant" in text:
        return ("Google revoked or expired the saved access (invalid_grant). Apps in Testing mode lose access "
                "after 7 days. Reconnect Gmail.")
    return text


def test_connection():
    """Count alert emails matching the search (nothing is saved). Raises GmailAuthRequired when not connected."""
    import agent_settings
    from gmail_parser import count_alert_messages, get_gmail_service

    service = get_gmail_service(interactive=False)
    email = service.users().getProfile(userId="me").execute().get("emailAddress")
    count = count_alert_messages(service)
    update_gmail_state(email=email, status="connected", reason="", last_test=now(), last_test_count=count)
    return {"ok": True, "email": email, "count": count, "query": agent_settings.gmail_query()}


def disconnect():
    """Revoke the token at Google, then delete token.json. Returns whether Google confirmed the revoke."""
    creds = load_credentials()
    revoked, message = False, ""
    if creds:
        token = creds.refresh_token or creds.token
        try:
            response = requests.post(REVOKE_URL, params={"token": token},
                                     headers={"content-type": "application/x-www-form-urlencoded"}, timeout=15)
            revoked = response.status_code == 200
            if not revoked:
                message = "Google did not confirm the revoke (the token may already be invalid)."
        except requests.RequestException as exc:
            message = f"Could not reach Google to revoke the token ({exc}). It was removed from this computer."
    TOKEN_PATH.unlink(missing_ok=True)
    update_gmail_state(status="not_connected", reason="", email=None, disconnected_at=now())
    return {"revoked": revoked, "message": message}
