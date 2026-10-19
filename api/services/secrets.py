"""Write-only management of the .env secrets the agent uses.

Values are never returned in full: reads give a masked hint only. Writes keep
every other line of .env (comments, Telegram keys, ...) untouched and also
update os.environ so the running server uses the new value immediately.
"""
import os
import re

from config import ENV_PATH, atomic_write_text

MANAGED = {
    "GROQ_API_KEY": ("Groq API key", "groq"),
    "ADZUNA_APP_ID": ("Adzuna app ID", "adzuna"),
    "ADZUNA_APP_KEY": ("Adzuna app key", "adzuna"),
    "ALERT_EMAIL_FROM": ("Alert sender (Gmail address)", "smtp"),
    "ALERT_EMAIL_PASS": ("Gmail app password", "smtp"),
    "ALERT_EMAIL_TO": ("Alert recipient", "smtp"),
}
PLACEHOLDER = re.compile(r"^your_|_here$")
LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


def get(key):
    value = os.environ.get(key, "")
    return "" if PLACEHOLDER.search(value or "") else value


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


def update(values):
    """Set (non-empty string) or clear (None or "") managed keys."""
    for key, value in values.items():
        if key not in MANAGED:
            raise KeyError(key)
        if value and ("\n" in value or "\r" in value):
            raise ValueError(f"{MANAGED[key][0]} cannot contain line breaks.")
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    pending = {key: (value or "").strip() for key, value in values.items()}
    output = []
    for line in lines:
        match = LINE.match(line)
        if match and match.group(1) in pending:
            key = match.group(1)
            value = pending.pop(key)
            if value:
                output.append(f"{key}={_quote(value)}")
            continue
        output.append(line)
    for key, value in pending.items():
        if value:
            output.append(f"{key}={_quote(value)}")
    atomic_write_text(ENV_PATH, "\n".join(output) + "\n")
    for key, value in values.items():
        if value and value.strip():
            os.environ[key] = value.strip()
        else:
            os.environ.pop(key, None)
