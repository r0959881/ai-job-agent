"""Web search: Brave first, Groq when Brave's quota is spent, and only real postings kept."""
import json

import pytest

import agent_settings
import discovery
from job_sources import sites, websearch


def context(regions=("BE",)):
    _settings, ctx = discovery.run_scope(agent_settings.load(), list(regions), ["Data Analyst"], 168)
    return ctx


@pytest.fixture(autouse=True)
def fresh_engine(monkeypatch):
    monkeypatch.setattr(websearch, "_brave_paused_until", 0.0)
    monkeypatch.setattr(sites, "DETAIL_PAUSE", 0)


def test_listing_pages_and_sites_with_their_own_source_are_skipped():
    assert websearch.is_candidate("https://jobs.lever.co/acme/123", "Acme - Data Analyst")
    assert not websearch.is_candidate("https://be.linkedin.com/jobs/view/1", "Data Analyst at Acme")
    assert not websearch.is_candidate("https://example.com/x", "120 Data Analyst jobs in Belgium")
    assert not websearch.is_candidate("https://example.com/search?q=data", "Data Analyst")


def test_only_postings_in_the_region_are_kept(monkeypatch):
    posting = lambda town: {"@type": "JobPosting", "title": "Data Analyst", "hiringOrganization": {"name": "Acme"},
                            "jobLocation": {"address": {"addressLocality": town}}}
    pages = {"https://jobs.lever.co/acme/1": posting("Ghent, Belgium"), "https://jobs.lever.co/acme/2": posting("Paris")}
    monkeypatch.setattr(sites, "_get", lambda url, params=None, browser=False:
                        f'<script type="application/ld+json">{json.dumps(pages[url])}</script>')
    monkeypatch.setattr(websearch, "brave_search", lambda query, key, hours: [
        ("https://jobs.lever.co/acme/1/apply", "Data Analyst"), ("https://jobs.lever.co/acme/2", "Data Analyst")])
    monkeypatch.setenv("BRAVE_API_KEY", "brave")
    ctx = context()

    searches = websearch.plan(ctx)
    jobs = searches[0].fetch()
    assert [job["url"] for job in jobs] == ["https://jobs.lever.co/acme/1"]  # /apply dropped, Paris left out
    assert jobs[0]["location"] == "Ghent, Belgium" and jobs[0]["company_name"] == "Acme"


def test_groq_takes_over_when_brave_is_out_of_quota_but_only_twice_per_run(monkeypatch):
    def spent(*_args):
        raise websearch.QuotaExceeded("429")

    groq_calls = []
    monkeypatch.setattr(websearch, "brave_search", spent)
    monkeypatch.setattr(websearch, "groq_search", lambda query, key, hours: groq_calls.append(query) or [])
    engine = websearch.Engine("brave", "gsk")
    assert [engine.search("q", 48)[1] for _ in range(3)] == ["Groq", "Groq", "Groq"]
    assert len(groq_calls) == websearch.GROQ_SEARCHES_PER_RUN == 2

    with pytest.raises(websearch.QuotaExceeded):  # no Groq key to fall back on
        websearch.Engine("brave", "").search("q", 48)


def test_without_any_key_web_search_is_skipped(monkeypatch):
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert websearch.plan(context()) == [] and not websearch.configured()
