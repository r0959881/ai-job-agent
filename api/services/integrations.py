"""Health of the external services: Groq, Adzuna, Gmail and SMTP alerts."""
import agent_settings
from api.services import secrets
from config import CREDENTIALS_PATH, TOKEN_PATH


def _health(status, message, action=None):
    return {"status": status, "message": message, **({"action": action} if action else {})}


def groq_status():
    key = secrets.get("GROQ_API_KEY")
    if not key:
        return _health("missing", "No Groq API key, so CVs cannot be tailored.", "/settings/integrations")
    if not key.startswith("gsk_"):
        return _health("error", "The Groq key does not look valid (it should start with gsk_).", "/settings/integrations")
    return _health("ok", "Groq key set.")


def adzuna_status():
    if not secrets.get("ADZUNA_APP_ID") or not secrets.get("ADZUNA_APP_KEY"):
        return _health("missing", "No Adzuna app ID or key, so Adzuna is skipped.", "/settings/integrations")
    if not agent_settings.get("sources").get("adzuna"):
        return _health("warning", "Adzuna is turned off in Settings → Search.", "/settings/search")
    return _health("ok", "Adzuna keys set.")


def gmail_status():
    from gmail_parser import read_gmail_state

    state = read_gmail_state()
    if not CREDENTIALS_PATH.exists():
        return _health("missing", "credentials.json is missing, so Gmail cannot be connected.", "/settings/integrations#gmail")
    if not TOKEN_PATH.exists():
        return _health("missing", "Gmail is not connected.", "/settings/integrations#gmail")
    if state.get("status") == "reauth_required":
        return _health("warning", "Google needs you to reconnect Gmail.", "/settings/integrations#gmail")
    if state.get("status") == "error":
        return _health("error", state.get("reason") or "The last Gmail check failed.", "/settings/integrations#gmail")
    return _health("ok", "Gmail connected.")


def smtp_status():
    configured = all(secrets.get(k) for k in ("ALERT_EMAIL_FROM", "ALERT_EMAIL_PASS", "ALERT_EMAIL_TO"))
    enabled = agent_settings.get("alerts").get("smtp_enabled")
    if not enabled:
        return _health("missing" if not configured else "warning", "Email alerts are off.", "/settings/integrations")
    if not configured:
        return _health("error", "Email alerts are on, but the Gmail address or app password is missing.",
                       "/settings/integrations")
    return _health("ok", "Email alerts on.")


def status():
    return {"groq": groq_status(), "adzuna": adzuna_status(), "gmail": gmail_status(), "smtp": smtp_status()}
