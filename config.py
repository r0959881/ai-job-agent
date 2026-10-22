"""Project-wide paths and small file helpers.

Every path is anchored to the folder that contains this file, so the agent
behaves the same no matter which directory it is started from.
"""
import html
import os
import re
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
    """The master resume as plain data, or None. A signed-in web user's resume comes from the database."""
    import user_scope

    scope = user_scope.current()
    if scope is not None and path is None:
        from api import store

        text = scope.cached("resume_text", lambda: store.get_resume_text(scope.user_id))
        return (yaml.safe_load(text) or {}) if text.strip() else None
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


# Gender markers job titles carry: "(H/F/X)", "M/V/X", "(m/w/d)", "FH", "FMX".
_GENDER = re.compile(r"[\(\[]?\b(?:[hfmvwxd](?:\s*/\s*[hfmvwxd]){1,2}|fh|hf|fmx|mfx|mvx|hfx|fhx)\b[\)\]]?", re.I)
_TITLE_NOISE = re.compile(r"\b(?:hybrid|hybride|remote|full[- ]?time|part[- ]?time|vast contract|cdi|cdd)\b"
                          r"|\d[\d.,]*\s*k?\s*(?:-|–|to)\s*\d[\d.,]*\s*k\b.*$|[€$£]\s*\d.*$|\d+\s*k\b.*$", re.I)
_LEGAL = re.compile(r"\s+\b(?:nv|sa|bv|bvba|srl|sprl|gmbh|ltd|llc|inc|plc|ag|sas|b\.v\.|n\.v\.|s\.a\.)\.?$", re.I)
DOCUMENT_KEYS = {"cv": "CV", "cover_letter": "CL"}


def _plain(text):
    return " ".join("".join(c if c.isalnum() or c in " -&+#." else " " for c in str(text or "")).split())


def clean_job_title(title, company=""):
    """'Data Engineer FHViveris Le Faubourg de Bruxelles Hybrid40K-45K year' -> 'Data Engineer'.

    Scraped titles often run on into the company, place, salary and a gender marker.
    """
    parsed = parse_alert_line(title)
    text = parsed["title"] if parsed else str(title or "").replace("\xad", "")
    company = _LEGAL.sub("", str(company or "")).strip()
    if company and len(company) > 2:  # everything from the company name on is not the title
        cut = text.lower().find(company.lower())
        if cut > 0:
            text = text[:cut]
    # LinkedIn alerts glue the marker to the company: "Data Engineer F/HViveris · Brussels". The title ends there.
    text = re.split(r"\b(?:[FHMVW]/[FHMVWX](?:/[FHMVWXD])?|FH|HF|FMX|MVX)(?=[A-Z][a-z])", text)[0]
    text = _TITLE_NOISE.sub(" ", _GENDER.sub(" ", text))
    # "Title | Brussels", "Title · Brussels", "Title - Ghent"
    text = re.split(r"\s*[|·•]\s*|\s+[–—]\s+|\s+-\s+(?=[A-Z][a-z]+(?:,|$))", text)[0]
    words = _plain(text).strip(" -.").split()
    short = ""
    for word in words:  # whole words, at most 60 characters
        if len(short) + len(word) + 1 > 60:
            break
        short = f"{short} {word}".strip()
    return short or _plain(title)[:60].strip() or "Job"


_MARKER = r"\b(?:[FHMVW]/[FHMVWX](?:/[FHMVWXD])?|FH|HF|FMX|MVX)"
# Words written in CamelCase on purpose: a capital inside them is not where the company starts.
_CAMEL_WORDS = {"devops", "mlops", "dataops", "finops", "devsecops", "pyspark", "bigquery", "powerbi", "sharepoint",
                "javascript", "typescript", "github", "gitlab", "linkedin", "nosql", "postgresql", "mysql", "openai",
                "databricks", "dbt", "sap", "iot", "etl", "elt", "ai", "it", "ml", "bi", "qa", "ux", "ui", "erp",
                "crm", "hr", "r&d", "m&a", "sql", "aws", "gcp", "api", "apis", "saas", "b2b", "b2c"}
# LinkedIn alert lines: "Consultant Data EngineerSia · Antwerp (Hybrid)Actively recruitingEasy Apply https://..."
_ALERT_LINE = re.compile(r"^(?P<head>[^·\n]+?)\s*·\s*(?P<place>[^(·\n]+?)\s*(?:\(|$|(?<=[a-z])(?=[A-Z0-9]))")


def parse_alert_line(text):
    """The title, company and place in a LinkedIn alert line, or None when the text is not one.

    The alert glues the company to the title ("Consultant Data EngineerSia"); it is split after
    the gender marker, or where a capital first follows a letter, digit or ")" with no space.
    """
    match = _ALERT_LINE.match(" ".join(html.unescape(str(text or "")).replace("\xad", "").split()))
    if not match:
        return None
    head, company = match.group("head").strip(), ""
    marker = re.search(rf"{_MARKER}(?=[A-Z][a-z])", head)
    if marker:
        head, company = head[:marker.start()].strip(), head[marker.end():].strip()
    else:
        for glue in re.finditer(r"(?<=[a-z0-9)])(?=[A-Z])", head):
            word_start = head.rfind(" ", 0, glue.start()) + 1
            word_end = (head.find(" ", glue.start()) + 1 or len(head) + 1) - 1
            if head[word_start:word_end].lower().strip("()/") not in _CAMEL_WORDS:
                head, company = head[:glue.start()].strip(), head[glue.start():].strip()
                break
    return {"title": head, "company": company, "place": _town(match.group("place"))}


def _town(place):
    """'Lokeren, Flemish Region, Belgium' -> 'Lokeren'; 'Brussels Region' -> 'Brussels'; regions alone -> ''."""
    town = re.sub(r"^Arrondissement of\s+", "", str(place or "").split(",")[0].strip(), flags=re.I)
    town = re.sub(r"\s+(?:Metropolitan Area|Area|Region|Capital Region)$", "", town, flags=re.I)
    return "" if town.lower() in {"belgium", "flemish", "walloon", "remote", "hybrid", "unknown", "netherlands"} else town


def company_in_title(title):
    """'Consultant Data EngineerSia · Antwerp' -> 'Sia': the company LinkedIn alerts glue to the title, or ''."""
    parsed = parse_alert_line(title)
    if parsed and parsed["company"]:
        return parsed["company"]
    match = re.search(rf"{_MARKER}([A-Z][^·|•(]+)", str(title or ""))
    return match.group(1).strip() if match else ""


def place_of(location, title=""):
    """The town for a letter's address: 'Antwerp' from 'Antwerp, Belgium' or from an alert line; '' if unclear."""
    text = " ".join(str(location or "").split())
    if text and "http" not in text and "·" not in text and len(text) <= 60:
        return _town(text)
    parsed = parse_alert_line(text) or parse_alert_line(title)
    return parsed["place"] if parsed and len(parsed["place"]) <= 40 else ""


def document_stem(job_title, company, kind):
    """'Data Engineer_Viveris_CV': the job title, the company and a short key for the document type."""
    if not company or str(company).startswith("Partner ("):
        company = company_in_title(job_title)
    company = _plain(_LEGAL.sub("", re.sub(r"^via\s+", "", str(company or ""), flags=re.I)))[:40].strip(" -.")
    parts = [clean_job_title(job_title, company), company, DOCUMENT_KEYS[kind]]
    return "_".join(part for part in parts if part)


def long_path(path):
    r"""Prefix absolute Windows paths with \\?\ so names past 260 characters still save."""
    text = str(Path(path).resolve())
    if os.name == "nt" and not text.startswith("\\\\?\\"):
        return "\\\\?\\" + text
    return text
