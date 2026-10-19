"""Project-wide paths and small file helpers.

Every path is anchored to the folder that contains this file, so the agent
behaves the same no matter which directory it is started from.
"""
import os
import tempfile
import time
from pathlib import Path

import yaml

CODE_ROOT = Path(__file__).resolve().parent
# Tests point AI_JOB_AGENT_ROOT at a temporary copy; normally data lives next to the code.
PROJECT_ROOT = Path(os.environ.get("AI_JOB_AGENT_ROOT") or CODE_ROOT).resolve()
DB_PATH = PROJECT_ROOT / "jobs.db"
OUTPUT_DIR = PROJECT_ROOT / "output"
RUNS_DIR = OUTPUT_DIR / "runs"
RESUME_PATH = PROJECT_ROOT / "resume_data.yaml"
SETTINGS_PATH = PROJECT_ROOT / "agent_settings.yaml"
ENV_PATH = PROJECT_ROOT / ".env"
CREDENTIALS_PATH = PROJECT_ROOT / "credentials.json"
TOKEN_PATH = PROJECT_ROOT / "token.json"
GMAIL_STATE_PATH = PROJECT_ROOT / ".gmail_state.json"
UI_TOKEN_PATH = PROJECT_ROOT / ".ui_token"
BACKUPS_DIR = PROJECT_ROOT / "backups"
WEB_DIST = CODE_ROOT / "web" / "dist"


def resolve_project_path(path):
    """Resolve a stored path (often 'output/x.docx') against the project root."""
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def relative_to_project(path):
    """Return the 'output/x.docx' style string that older code stores and prints."""
    path = Path(path)
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)


def atomic_write_text(path, text, encoding="utf-8"):
    """Write to a temp file in the same folder, then replace the target.

    OneDrive can briefly lock files while syncing, so replacing is retried.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as handle:
            handle.write(text)
        for attempt in range(10):
            try:
                os.replace(temp_name, path)
                return path
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.1 * (attempt + 1))
    finally:
        if os.path.exists(temp_name):
            os.remove(temp_name)
    return path


def load_resume_file(path=None):
    path = Path(path or RESUME_PATH)
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def file_name_slug(full_name=None):
    """'Ammar Haider' -> 'Ammar_Haider', used as the prefix of generated files."""
    if full_name is None:
        data = load_resume_file() or {}
        full_name = (data.get("personal_info") or {}).get("full_name") or ""
    cleaned = "".join(c for c in str(full_name) if c.isalnum() or c in " -_").strip()
    return "_".join(cleaned.split()) or "Candidate"


def long_path(path):
    r"""Prefix absolute Windows paths with \\?\ so names past 260 characters still save."""
    text = str(Path(path).resolve())
    if os.name == "nt" and not text.startswith("\\\\?\\"):
        return "\\\\?\\" + text
    return text
