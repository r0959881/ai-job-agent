"""Server settings, read from environment variables (or the .env file next to the app).

On cPanel these are set under Setup Python App → Environment variables. Every
value has a safe default for running locally, except that a hosted server must
set SECRET_KEY and PUBLIC_URL.
"""
import os
import secrets
from functools import lru_cache
from urllib.parse import urlparse

from dotenv import load_dotenv

from config import ENV_PATH, GMAIL_STATE_PATH, PROJECT_ROOT, atomic_write_text

load_dotenv(ENV_PATH)

SECRET_KEY_FILE = PROJECT_ROOT / ".secret_key"


def env(name, default=""):
    return (os.environ.get(name) or default).strip()


def _flag(name):
    return env(name).lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def secret_key():
    """Signs session cookies and derives the key that encrypts users' API keys.

    Without SECRET_KEY a random key is created once in .secret_key, which is fine
    locally. On a server set SECRET_KEY: changing it signs everyone out and makes
    stored API keys unreadable (users then re-enter them).
    """
    value = env("SECRET_KEY")
    if value:
        return value
    try:
        stored = SECRET_KEY_FILE.read_text(encoding="utf-8").strip()
        if stored:
            return stored
    except OSError:
        pass
    value = secrets.token_urlsafe(48)
    atomic_write_text(SECRET_KEY_FILE, value)
    return value


def database_url():
    """MySQL on cPanel (mysql+pymysql://user:password@localhost/name?charset=utf8mb4); SQLite locally."""
    return env("DATABASE_URL") or f"sqlite:///{(PROJECT_ROOT / 'app.db').as_posix()}"


def public_url():
    """The address users open, e.g. https://jobs.example.com. Used for OAuth redirect URIs."""
    return env("PUBLIC_URL").rstrip("/")


def cookie_secure():
    if env("COOKIE_SECURE"):
        return _flag("COOKIE_SECURE")
    return public_url().startswith("https://")


def allowed_hosts():
    """Host names the server answers to. Defaults to PUBLIC_URL's host plus localhost."""
    hosts = {host.strip().lower() for host in env("ALLOWED_HOSTS").split(",") if host.strip()}
    if public_url():
        hosts.add((urlparse(public_url()).hostname or "").lower())
    return hosts | {"127.0.0.1", "localhost", "testserver"}


def oauth_client(provider):
    """(client_id, client_secret) for 'google' or 'linkedin', or None when not configured."""
    prefix = provider.upper()
    client_id, client_secret = env(f"{prefix}_CLIENT_ID"), env(f"{prefix}_CLIENT_SECRET")
    return (client_id, client_secret) if client_id and client_secret else None


LOCAL_PROVIDER = "local"


def local_mode():
    """Running on your own PC with `start.ps1` / `python serve.py` (never set on a server).

    You are signed in automatically as the local account, which works on the project's own
    files: resume_data.yaml, agent_settings.yaml, the keys in .env, jobs.db and output/.
    """
    return _flag("AI_JOB_AGENT_LOCAL")


def project_owner_email():
    """The account that owns this PC's project files in local mode.

    AI_JOB_AGENT_LOCAL_EMAIL, or else the Gmail account the command line is connected to.
    Signing in locally with this email (automatically, with the developer sign-in or with
    Google) opens resume_data.yaml, agent_settings.yaml, .env, jobs.db and output/.
    """
    email = env("AI_JOB_AGENT_LOCAL_EMAIL").lower()
    if not email:
        try:
            import json

            email = str(json.loads(GMAIL_STATE_PATH.read_text(encoding="utf-8")).get("email") or "").lower()
        except (OSError, ValueError, AttributeError):
            email = ""
    return email if "@" in email else ""


def dev_login_enabled():
    """A sign-in form without Google or LinkedIn, for local development and tests only."""
    return _flag("AI_JOB_AGENT_DEV_LOGIN")


def email_allowed(email):
    """ALLOWED_EMAILS limits who can sign up: addresses or @domains, comma separated. Empty allows everyone."""
    rules = [rule.strip().lower() for rule in env("ALLOWED_EMAILS").split(",") if rule.strip()]
    if not rules:
        return True
    email = (email or "").lower()
    return any(email == rule or (rule.startswith("@") and email.endswith(rule)) for rule in rules)


def search_time_budget():
    """Seconds one search request may spend on detail pages, so it ends before the host's request timeout."""
    try:
        return max(5.0, float(env("SEARCH_TIME_BUDGET", "35")))
    except ValueError:
        return 35.0
