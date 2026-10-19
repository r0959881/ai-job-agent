"""Editable search settings stored in agent_settings.yaml.

DEFAULTS mirrors the constants that used to be hard-coded in discovery.py,
database.py and gmail_parser.py. A missing file or a missing key falls back to
these values, so behaviour is identical until the settings are edited.
"""
import copy
import threading

import yaml

from config import SETTINGS_PATH, atomic_write_text

DEFAULTS = {
    "target_roles": {
        "Data Integration": [
            "data integration", "integration engineer", "etl developer",
            "etl engineer", "data ingestion", "integration specialist",
        ],
        "Data Science": [
            "data science", "data scientist", "machine learning",
            "machine learning engineer", "predictive analytics",
        ],
        "Data Engineer": [
            "data engineer", "analytics engineer", "data platform",
            "data pipeline", "data pipelines", "data architect",
        ],
        "Data Analyst": [
            "data analyst", "bi analyst", "bi engineer", "business intelligence",
            "reporting analyst", "analytics specialist",
        ],
        "Functional Analyst (IT)": [
            "functional analyst", "it functional analyst", "business systems analyst",
            "requirements analyst", "functional consultant",
        ],
    },
    "extra_keywords": [
        "databricks", "pyspark", "fabric", "power bi", "sql", "python",
        "data modelling", "data modeling", "etl", "elt",
    ],
    "search_queries": {
        "Data Integration": ["data integration", "ETL developer"],
        "Data Science": ["data scientist", "machine learning"],
        "Data Engineer": ["data engineer", "data platform"],
        "Data Analyst": ["data analyst", "business intelligence"],
        "Functional Analyst (IT)": ["functional analyst", "business systems analyst"],
    },
    "entry_level_keywords": [
        "junior", "trainee", "traineeship", "intern", "internship", "graduate",
        "starter", "entry level", "entry-level", "early career",
    ],
    "exclude_title_keywords": [
        "director", "senior manager", "head of", "lead", "vp", "chief",
        "principal", "senior", "manager", "paid search", "marketing manager",
        "sales executive", "recruiter", "hr manager", "account manager",
    ],
    "allowed_locations": [
        "belgium", "belgië", "belgique", "mechelen", "antwerp", "antwerpen",
        "brussels", "bruxelles", "ghent", "gent", "leuven", "flanders", "vlaanderen",
        "netherlands", "nederland", "amsterdam", "rotterdam", "utrecht", "eindhoven",
    ],
    "blocked_locations": [
        "germany", "deutschland", "düsseldorf", "dusseldorf", "berlin", "munich",
        "münchen", "frankfurt", "hamburg", "cologne", "köln", "stuttgart",
        "france", "paris", "uk", "united kingdom", "england", "scotland", "wales",
        "london", "manchester", "birmingham", "leeds", "edinburgh", "glasgow", "bristol",
    ],
    "trusted_alert_sources": [
        "StepStone Belgium", "Jobat Belgium", "VDAB Belgium", "Actiris Brussels",
        "Indeed Alerts", "LinkedIn Alerts",
    ],
    "time_window_hours": 48,
    "sources": {"adzuna": True, "arbeitnow": True, "gmail": True},
    "adzuna": {"country": "be", "location": "Belgium", "results_per_page": 50},
    "gmail": {
        "senders": [
            "linkedin.com", "indeed.com", "stepstone.be", "jobat.be",
            "vdab.be", "actiris.brussels",
        ],
        "lookback_days": 2,
        "max_results": 100,
    },
    # Empty means "use the built-in ROLE_LETTERS in generate_cover_letter.py".
    "cover_letters": {},
    "alerts": {"smtp_enabled": False},
}

_lock = threading.Lock()
_cache = {"mtime": None, "path": None, "data": None}


def _merge(defaults, override):
    if not isinstance(override, dict):
        return copy.deepcopy(defaults)
    merged = copy.deepcopy(defaults)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict) and key in {
            "sources", "adzuna", "gmail", "alerts",
        }:
            merged[key] = {**merged[key], **value}
        elif value is not None:
            merged[key] = value
    return merged


def load(path=None):
    """Return the effective settings (file values over DEFAULTS), cached by mtime."""
    path = path or SETTINGS_PATH
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        return copy.deepcopy(DEFAULTS)
    with _lock:
        if _cache["path"] == path and _cache["mtime"] == mtime:
            return copy.deepcopy(_cache["data"])
        try:
            with open(path, encoding="utf-8") as handle:
                raw = yaml.safe_load(handle) or {}
        except (OSError, yaml.YAMLError):
            raw = {}
        data = _merge(DEFAULTS, raw)
        _cache.update(mtime=mtime, path=path, data=data)
        return copy.deepcopy(data)


def get(key, path=None):
    return load(path)[key]


HEADER = (
    "# AI Job Agent search settings. Edit here or in the web UI (Settings -> Search).\n"
    "# Any key you delete falls back to the built-in default.\n"
)


def dump(data):
    return HEADER + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)


def save(data, path=None):
    path = path or SETTINGS_PATH
    atomic_write_text(path, dump(data))
    with _lock:
        _cache.update(mtime=None, path=None, data=None)
    return load(path)


def seed(path=None, cover_letters=None):
    """Create the settings file from DEFAULTS if it does not exist yet."""
    path = path or SETTINGS_PATH
    if path.exists():
        return False
    data = copy.deepcopy(DEFAULTS)
    if cover_letters:
        data["cover_letters"] = copy.deepcopy(cover_letters)
    save(data, path)
    return True


def all_target_keywords(settings=None):
    settings = settings or load()
    keywords = [kw for kws in settings["target_roles"].values() for kw in kws]
    return keywords + list(settings["extra_keywords"])


def gmail_query(settings=None):
    settings = settings or load()
    gmail = settings["gmail"]
    senders = " ".join(f"from:{sender}" for sender in gmail["senders"])
    return f"newer_than:{gmail['lookback_days']}d {{{senders}}}"
