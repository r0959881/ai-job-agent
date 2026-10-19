"""Offline fakes for UI development and end-to-end tests.

Enabled only when AI_JOB_AGENT_FAKE_SOURCES=1. Replaces Adzuna/Arbeitnow HTTP
calls, the Groq client and the Gmail service with deterministic stand-ins, so a
full run works without network access or API keys. Never active by default.
"""
import base64
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


class _Completions:
    def create(self, **_kwargs):
        time.sleep(float(os.environ.get("AI_JOB_AGENT_FAKE_GROQ_DELAY", "1.0")))
        content = ("SUMMARY: Data professional with hands-on SQL, Python and Power BI experience who turns raw data "
                   "into reliable reporting. Comfortable across ETL, modelling and stakeholder communication. "
                   "Eager to grow in a junior data role in Belgium.\nBULLETS:\n"
                   "- Designed Power BI dashboards used by 50+ business users.\n"
                   "- Wrote SQL to clean and shape operational data before reporting.\n"
                   "- Replaced a 12-week manual workflow with a single-click solution.\n"
                   "- Documented metric logic and data definitions for onboarding.")
        message = type("M", (), {"content": content})
        return type("R", (), {"choices": [type("C", (), {"message": message})]})


class FakeGroq:
    def __init__(self, api_key=None):
        self.chat = type("Chat", (), {"completions": _Completions()})()


class _Exec:
    def __init__(self, value):
        self.value = value

    def execute(self):
        return self.value


class FakeGmailService:
    def users(self):
        html = ('<html><body><p><a href="https://www.linkedin.com/jobs/view/1">Junior BI Analyst</a> '
                'Mechelen, Belgium</p></body></html>')
        encoded = base64.urlsafe_b64encode(html.encode()).decode()

        class Messages:
            def list(self, **_kwargs):
                return _Exec({"messages": [{"id": "demo"}]})

            def get(self, **_kwargs):
                return _Exec({"payload": {"headers": [{"name": "From", "value": "jobalerts-noreply@linkedin.com"}],
                                          "mimeType": "text/html", "body": {"data": encoded}}})

        class Users:
            def messages(self):
                return Messages()

            def getProfile(self, userId):
                return _Exec({"emailAddress": "demo@example.com", "messagesTotal": 42})

        return Users()


def install():
    """Patch the pipeline modules in this process. Returns True when fakes were installed."""
    if not enabled():
        return False
    import discovery
    import gmail_parser
    import main
    import tailor

    os.environ.setdefault("GROQ_API_KEY", "gsk_fake_for_demo")
    os.environ.setdefault("ADZUNA_APP_ID", "demo")
    os.environ.setdefault("ADZUNA_APP_KEY", "demo")
    discovery.requests.get = _fake_get
    tailor.Groq = FakeGroq
    main.get_client = lambda: FakeGroq()
    gmail_parser.get_gmail_service = lambda interactive=True: FakeGmailService()
    return True
