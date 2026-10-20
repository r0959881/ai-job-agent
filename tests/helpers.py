"""Fakes for the HTTP sources, Groq and Gmail used across tests."""
import base64
from datetime import UTC, datetime


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


def fake_get(url, params=None, timeout=None, **_kwargs):
    now = datetime.now(UTC).isoformat()
    if "adzuna" in url:
        what = params["what"]
        return FakeResponse({"results": [
            {"title": f"Junior {what.title()}", "company": {"display_name": f"Acme {what}"},
             "description": "Junior role with SQL and Python", "location": {"display_name": "Antwerp, Belgium"},
             "redirect_url": f"https://example.com/{what.replace(' ', '-')}", "created": now},
            {"title": f"Senior {what.title()}", "company": {"display_name": "BigCo"},
             "description": "senior", "location": {"display_name": "Brussels"}, "redirect_url": "https://x"},
        ]})
    return FakeResponse({"data": [
        {"title": "Junior Data Engineer", "company_name": "Gent BV", "description": "junior python",
         "location": "Gent, Belgium", "url": "https://b"},
    ]})


def fake_scrape(**kwargs):
    """Stand-in for JobSpy: one junior posting per search, the same job on every site and region."""
    import re

    term = kwargs["search_term"]
    phrase = (re.findall(r'"([^"]+)"', term) or [term])[0]
    return [{
        "title": f"Junior {phrase.title()}", "company": f"Scraped {phrase.title()} NV",
        "location": f"Capital City, {kwargs.get('location', '')}", "job_url": f"https://jobs.example.com/{phrase}",
        "description": f"Junior {phrase} role. SQL and Python.", "date_posted": datetime.now(UTC).date(),
        "job_level": "entry level", "is_remote": False,
    }]


class FakeCompletions:
    def __init__(self, on_call=None, fail=None):
        self.calls = 0
        self.on_call = on_call
        self.fail = fail

    def create(self, **_kwargs):
        self.calls += 1
        if self.on_call:
            self.on_call(self.calls)
        if self.fail:
            raise self.fail
        message = type("M", (), {"content": "SUMMARY: Tailored summary.\nBULLETS:\n- Bullet one\n- Bullet two"})
        return type("R", (), {"choices": [type("C", (), {"message": message})]})


class FakeGroq:
    def __init__(self, on_call=None, fail=None):
        self.completions = FakeCompletions(on_call, fail)
        self.chat = type("Chat", (), {"completions": self.completions})()


def alert_html(*links):
    body = "".join(f'<p><a href="{href}">{text}</a> Antwerp Belgium</p>' for text, href in links)
    return base64.urlsafe_b64encode(f"<html><body>{body}</body></html>".encode()).decode()


class _Exec:
    def __init__(self, value):
        self.value = value

    def execute(self):
        return self.value


class FakeGmailService:
    def __init__(self, links=(("Junior Data Engineer", "https://linkedin.com/jobs/1"),), email="me@example.com"):
        self.encoded = alert_html(*links)
        self.email = email
        self.queries = []

    def users(self):
        service = self

        class Users:
            def messages(self):
                class Messages:
                    def list(self, **kwargs):
                        service.queries.append(kwargs.get("q"))
                        return _Exec({"messages": [{"id": "m1"}]})

                    def get(self, **_kwargs):
                        return _Exec({"payload": {"headers": [{"name": "From", "value": "jobs@linkedin.com"}],
                                                  "mimeType": "text/html", "body": {"data": service.encoded}}})

                return Messages()

            def getProfile(self, userId):
                return _Exec({"emailAddress": service.email, "messagesTotal": 10})

        return Users()


def fake_site_search(source, query, ctx, region, _cache=None):
    """Stand-in for the StepStone, VDAB, Michael Page and Jobat adapters: one junior posting per search."""
    return [{
        "title": f"Junior {query.title()}", "company_name": f"{source.title()} Client NV",
        "description": f"Junior {query} role. SQL and Python.", "location": f"Capital City, {region['label']}",
        "url": f"https://{source}.example.com/{query.replace(' ', '-')}", "created": datetime.now(UTC).isoformat(),
    }]


def install_fakes(monkeypatch, groq=None, gmail=None):
    """Patch network calls. Returns the FakeGroq so tests can inspect calls."""
    import discovery
    import gmail_parser
    import main
    from job_sources import scrapers, sites

    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("ADZUNA_APP_ID", "id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "key")
    monkeypatch.setattr(discovery.requests, "get", fake_get)
    monkeypatch.setattr(scrapers, "_scrape", fake_scrape)
    monkeypatch.setattr(sites, "search", fake_site_search)
    groq = groq or FakeGroq()
    monkeypatch.setattr(main, "get_client", lambda: groq)
    if gmail is not False:  # False keeps the real get_gmail_service.
        service = gmail or FakeGmailService()
        monkeypatch.setattr(gmail_parser, "get_gmail_service", lambda interactive=True: service)
    return groq


# --- The signed-in test user's server data -------------------------------------------------

def user_id_for(email="tester@example.com"):
    import sqlalchemy as sa

    from api import store

    with store.engine().connect() as conn:
        row = conn.execute(sa.select(store.users.c.id).where(store.users.c.email == email)).first()
    assert row is not None, "sign in first (use the client fixture)"
    return row.id


def resume_text(email="tester@example.com"):
    from api import store

    return store.get_resume_text(user_id_for(email))


def set_resume_text(text, email="tester@example.com"):
    from api import store

    store.set_resume_text(user_id_for(email), text)


def set_secret(name, value, email="tester@example.com"):
    from api import store

    store.set_secret(user_id_for(email), name, value)
