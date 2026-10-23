"""Health of the services a user's runs depend on: Groq (their key) and Adzuna (optional keys)."""
import agent_settings
from api.services import secrets


def _health(status, message, action=None):
    return {"status": status, "message": message, **({"action": action} if action else {})}


def groq_status():
    key = secrets.get("GROQ_API_KEY")
    if not key:
        return _health("missing", "No Groq API key, so CVs cannot be tailored.", "/settings/integrations")
    if not key.startswith("gsk_"):
        return _health("error", "The Groq key does not look valid (it should start with gsk_).", "/settings/integrations")
    if secrets.get("GROQ_API_KEY_2").startswith("gsk_"):
        return _health("ok", "Groq key set, with a backup key for when it reaches its limit.")
    return _health("ok", "Groq key set.")


def adzuna_status():
    if not secrets.get("ADZUNA_APP_ID") or not secrets.get("ADZUNA_APP_KEY"):
        return _health("missing", "No Adzuna app ID or key, so Adzuna is skipped.", "/settings/integrations")
    if not agent_settings.get("sources").get("adzuna"):
        return _health("warning", "Adzuna is turned off in Settings → Search.", "/settings/search")
    return _health("ok", "Adzuna keys set.")


def status():
    return {"groq": groq_status(), "adzuna": adzuna_status()}
