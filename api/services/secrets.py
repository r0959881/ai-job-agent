"""API keys, write-only: encrypted in the server database for web users, in .env for the local account.

Values are never returned in full: reads give a masked hint only. Writes to .env
keep every other line untouched and update os.environ so they apply at once.
"""
import os
import re

import user_scope
from config import ENV_PATH, atomic_write_text

MANAGED = {
    "GROQ_API_KEY": ("Groq API key", "groq"),
    "ADZUNA_APP_ID": ("Adzuna app ID", "adzuna"),
    "ADZUNA_APP_KEY": ("Adzuna app key", "adzuna"),
}
PLACEHOLDER = re.compile(r"^your_|_here$")
LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


def get(key):
    value = user_scope.secret(key) or ""
    return "" if PLACEHOLDER.search(value) else value


def mask(value):
    if not value:
        return ""
    if "@" in value:
        name, _, domain = value.partition("@")
        return f"{name[:2]}…@{domain}"
    if len(value) <= 8:
        return "••••"
    return f"{value[:4]}…{value[-4:]}"


def describe():
    return [
        {"key": key, "label": label, "group": group, "set": bool(get(key)), "masked": mask(get(key))}
        for key, (label, group) in MANAGED.items()
    ]


def _quote(value):
    if re.search(r"[\s#\"'=]", value):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def _write_env(values):
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    pending = {key: (value or "").strip() for key, value in values.items()}
    output = []
    for line in lines:
        match = LINE.match(line)
        if match and match.group(1) in pending:
            value = pending.pop(match.group(1))
            if value:
                output.append(f"{match.group(1)}={_quote(value)}")
            continue
        output.append(line)
    output += [f"{key}={_quote(value)}" for key, value in pending.items() if value]
    atomic_write_text(ENV_PATH, "\n".join(output) + "\n")
    for key, value in values.items():
        if value and value.strip():
            os.environ[key] = value.strip()
        else:
            os.environ.pop(key, None)


def update(values):
    """Set (non-empty string) or clear (None or "") keys: the signed-in user's, or .env for the local account."""
    from api import store

    scope = user_scope.current()
    for key, value in values.items():
        if key not in MANAGED:
            raise KeyError(key)
        if value and ("\n" in value or "\r" in value):
            raise ValueError(f"{MANAGED[key][0]} cannot contain line breaks.")
        if value and len(value) > 500:
            raise ValueError(f"{MANAGED[key][0]} is too long.")
    if scope is None:
        _write_env(values)
        return
    for key, value in values.items():
        store.set_secret(scope.user_id, key, (value or "").strip())
        scope.forget(f"secret:{key}")
