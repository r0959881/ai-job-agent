"""Offline fakes for UI development and end-to-end tests.

Enabled only when AI_JOB_AGENT_FAKE_SOURCES=1. Replaces the job-source HTTP
calls, the JobSpy scraper, the job-site adapters and the Groq client with
deterministic stand-ins, so a full run works without network access or API
keys. Never active by default.
"""
import os
import time
from datetime import UTC, datetime

ENV_FLAG = "AI_JOB_AGENT_FAKE_SOURCES"


def enabled():
    return os.environ.get(ENV_FLAG) == "1"


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


def _fake_get(url, params=None, timeout=None, **_kwargs):
    now = datetime.now(UTC).isoformat()
    time.sleep(0.2)
    if "adzuna" in url:
        what = (params or {}).get("what", "data")
        return _Response({"results": [{
            "title": f"Junior {what.title()}",
            "company": {"display_name": f"Demo {what.title()} BV"},
            "description": f"Junior {what} role in Antwerp. SQL, Python and Power BI. 0-2 years of experience.",
            "location": {"display_name": "Antwerp, Belgium"},
            "redirect_url": f"https://example.com/jobs/{what.replace(' ', '-')}",
            "created": now,
            "salary_min": 3200, "salary_max": 4100,
        }]})
    return _Response({"data": [{
        "title": "Junior Data Engineer", "company_name": "Gent Data Works",
        "description": "Junior Python and SQL data pipelines in Gent.", "location": "Gent, Belgium",
        "url": "https://example.com/jobs/gent-data-engineer",
    }]})


def _fake_site_search(source, query, ctx, region, _cache=None):
    """StepStone, VDAB, Michael Page and Jobat stand-in: one junior posting per search phrase."""
    time.sleep(0.2)
    return [{
        "title": f"Junior {query.title()}", "company_name": f"Demo {query.title()} ({source.title()})",
        "description": f"Junior {query} role. SQL, Python and Power BI. 0-2 years of experience.",
        "location": f"Antwerp, {region['label']}", "url": f"https://example.com/{source}/{query.replace(' ', '-')}",
        "created": datetime.now(UTC).isoformat(),
    }]


def _fake_scrape(**kwargs):
    """JobSpy stand-in: one junior posting per search phrase."""
    import re

    time.sleep(0.3)
    term = kwargs["search_term"]
    phrase = (re.findall(r'"([^"]+)"', term) or [term])[0]
    site = kwargs["site_name"][0]
    return [{
        "title": f"Junior {phrase.title()}", "company": f"Demo {phrase.title()} ({site.title()})",
        "location": f"Brussels, {kwargs.get('location', '')}",
        "job_url": f"https://example.com/{site}/{phrase.replace(' ', '-')}",
        "description": f"Junior {phrase} role. SQL, Python and Power BI. 0-2 years of experience.",
        "date_posted": datetime.now(UTC).date(), "job_level": "entry level", "is_remote": False,
    }]


FAKE_RESUME = {
    "personal_info": {"full_name": "Demo Person", "headline": "Junior Data Analyst", "email": "demo@example.com",
                      "phone": "+32 400 00 00 00", "location": "Gent, Belgium"},
    "core_skills": {"languages_and_tools": ["SQL", "Python"], "bi_and_reporting": ["Power BI"]},
    "experience": [{"company": "Demo Retail NV", "role": "Data Analyst Intern", "location": "Gent",
                    "dates": "Feb 2026 - Jun 2026", "type": "Internship",
                    "bullets": ["Built Power BI dashboards for store managers.", "Cleaned sales data with SQL."]}],
    "projects": [{"title": "Sales Forecast", "tech_stack": "Python, Prophet", "highlights": ["Forecast weekly sales."]}],
    "certifications": [{"name": "PL-300 Power BI Data Analyst", "issuer": "Microsoft", "year": "2026"}],
    "education": {"degree": "Bachelor Business IT", "institution": "Demo University", "location": "Gent",
                  "dates": "2023 - 2026", "coursework": ["Databases"]},
    "languages": ["English: C1", "Dutch: B2"],
    "low_confidence": ["experience.0.dates"],
}


class _Completions:
    def create(self, **kwargs):
        prompt = kwargs.get("messages", [{}])[-1].get("content", "")
        if "Extract this resume into JSON" in prompt:
            import json

            return self._reply(json.dumps(FAKE_RESUME))
        if "clean up a LinkedIn profile export" in prompt:
            return self._reply('{"experience": [], "projects": [], "skill_categories": {}}')
        time.sleep(float(os.environ.get("AI_JOB_AGENT_FAKE_GROQ_DELAY", "1.0")))
        content = ("SUMMARY: Data professional with hands-on SQL, Python and Power BI experience who turns raw data "
                   "into reliable reporting. Comfortable across ETL, modelling and stakeholder communication. "
                   "Eager to grow in a junior data role in Belgium.\nBULLETS:\n"
                   "- Designed Power BI dashboards used by 50+ business users.\n"
                   "- Wrote SQL to clean and shape operational data before reporting.\n"
                   "- Replaced a 12-week manual workflow with a single-click solution.\n"
                   "- Documented metric logic and data definitions for onboarding.")
        return self._reply(content)

    @staticmethod
    def _reply(content):
        message = type("M", (), {"content": content})
        return type("R", (), {"choices": [type("C", (), {"message": message})]})


class FakeGroq:
    def __init__(self, api_key=None):
        self.chat = type("Chat", (), {"completions": _Completions()})()
        self.models = type("Models", (), {"list": lambda self: type("L", (), {"data": [1, 2, 3]})()})()


def install():
    """Patch the pipeline modules in this process. Returns True when fakes were installed."""
    if not enabled():
        return False
    import discovery
    import tailor
    from job_sources import scrapers, sites, websearch

    discovery.requests.get = _fake_get
    discovery.adzuna_credentials = lambda: ("demo", "demo")
    scrapers._scrape = _fake_scrape
    sites.search = _fake_site_search
    websearch.fetch = lambda query, ctx, region, _engine, _cache: []
    tailor.Groq = FakeGroq  # type: ignore[misc, assignment]
    tailor.get_client = lambda: FakeGroq()
    return True
