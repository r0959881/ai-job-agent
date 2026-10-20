"""Region/role scoping, the job-source adapters and the search catalog (all network mocked)."""
from datetime import UTC, datetime, timedelta

from helpers import FakeResponse, fake_scrape, install_fakes

import agent_settings


def collect():
    events = []
    return events, lambda step, status, message, data: events.append((step, status, message, data))


def final(events, step):
    return [e for e in events if e[0] == step and e[1] not in {"log", "progress", "started"}][-1]


def test_a_run_searches_only_the_chosen_regions_and_roles(monkeypatch):
    import main
    from job_sources import scrapers

    install_fakes(monkeypatch)
    calls = []
    monkeypatch.setattr(scrapers, "_scrape", lambda **kwargs: calls.append(kwargs) or fake_scrape(**kwargs))
    events, on_event = collect()
    summary = main.run_agent(on_event=on_event, interactive=False, options={
        "regions": ["DE"], "roles": ["Data Analyst"], "dry_run": True,
        "sources": ["linkedin", "indeed", "arbeitnow", "arbeitsagentur", "gmail"],
    })

    assert {call["location"] for call in calls} == {"Germany"}
    assert {call["site_name"][0] for call in calls} == {"linkedin", "indeed"}
    assert {call["search_term"] for call in calls} == {'"data analyst" OR "business intelligence"'}
    assert next(call for call in calls if call["site_name"] == ["indeed"])["country_indeed"] == "germany"
    boards = final(events, "boards")
    assert boards[1] == "succeeded" and set(boards[3]["per_source"]) == {"Arbeitnow", "Bundesagentur für Arbeit"}
    # The Belgian Arbeitnow and Gmail jobs are outside the chosen region, so only the German one is eligible.
    assert summary["eligible"] == 1
    assert final(events, "filter")[3]["eligible"] == 1


def test_a_failing_source_is_skipped_after_two_failures(monkeypatch):
    import main
    from job_sources import scrapers

    install_fakes(monkeypatch)
    attempts = []

    def flaky(**kwargs):
        if kwargs["site_name"] == ["linkedin"]:
            attempts.append(kwargs)
            raise RuntimeError("429 Too Many Requests")
        return fake_scrape(**kwargs)

    monkeypatch.setattr(scrapers, "_scrape", flaky)
    events, on_event = collect()
    summary = main.run_agent(on_event=on_event, interactive=False, options={
        "regions": ["BE"], "roles": ["Data Analyst", "Data Engineer", "Data Science"],
        "sources": ["linkedin", "indeed"], "dry_run": True,
    })
    assert len(attempts) == 2  # the third LinkedIn search is not even tried
    scrape = final(events, "scrape")
    assert scrape[1] == "warning" and "3 of 6 searches failed or were skipped" in scrape[2]
    assert scrape[3]["per_source"]["Indeed"]["new"] == 3
    assert summary["new"] == 3


def test_postings_older_than_the_window_are_dropped(monkeypatch):
    import main
    from job_sources import scrapers

    install_fakes(monkeypatch)
    old = datetime.now(UTC).date() - timedelta(days=10)
    monkeypatch.setattr(scrapers, "_scrape", lambda **kw: [{**fake_scrape(**kw)[0], "date_posted": old}])
    events, on_event = collect()
    main.run_agent(on_event=on_event, interactive=False, options={
        "regions": ["BE"], "roles": ["Data Analyst"], "sources": ["indeed"], "dry_run": True,
    })
    scrape = final(events, "scrape")[3]
    assert scrape["new"] == 0 and scrape["filtered"] == 1


def test_scraped_rows_keep_seniority_and_region():
    import regions
    from job_sources.scrapers import normalise

    item = normalise({"title": "BI Analyst", "company": "X", "location": "Zwijnaarde", "job_url": "u",
                      "description": "Power BI", "job_level": "entry level", "date_posted": None,
                      "min_amount": float("nan"), "is_remote": True}, regions.get("BE"))
    assert item["location"] == "Zwijnaarde (Remote), Belgium"
    assert item["description"].endswith("Seniority level: entry level")
    assert item["salary_min"] is None


def route(payloads):
    def fake_get(url, params=None, headers=None, timeout=None, **_kwargs):
        for fragment, payload in payloads.items():
            if fragment in url:
                return FakeResponse(payload)
        return FakeResponse({}, status=404)

    return fake_get


def test_board_adapters_normalise_their_payloads(monkeypatch):
    import requests

    import discovery
    from job_sources import boards

    now = datetime.now(UTC).isoformat()
    monkeypatch.setattr(requests, "get", route({
        "greenhouse.io": {"jobs": [{"title": "Data Analyst", "company_name": "Collibra",
                                    "content": "&lt;p&gt;Junior &amp;amp; SQL&lt;/p&gt;",
                                    "location": {"name": "Brussels, Belgium"}, "absolute_url": "https://gh/1",
                                    "first_published": now}]},
        "api.lever.co": [{"text": "Data Engineer", "descriptionPlain": "Pipelines",
                          "lists": [{"text": "You", "content": "<li>Python</li>"}],
                          "categories": {"location": "Ghent"}, "hostedUrl": "https://lever/1",
                          "createdAt": 1792425604000}],
        "pc/v6/jobs": {"ergebnisliste": [{"stellenangebotsTitel": "Junior Data Analyst (m/w/d)", "firma": "ACME",
                                          "referenznummer": "123-ABC",
                                          "stellenlokationen": [{"adresse": {"ort": "Rostock"}}],
                                          "datumErsteVeroeffentlichung": "2026-10-12"}]},
        "jobdetails": {"stellenangebotsBeschreibung": "Einstieg für Berufsanfänger"},
        "remotive.com": {"jobs": [{"title": "Data Analyst", "company_name": "R", "description": "<b>Hi</b>",
                                   "candidate_required_location": "Europe", "url": "https://r/1",
                                   "publication_date": now}]},
    }))

    greenhouse = boards.fetch_company_board("greenhouse", "collibra")[0]
    assert greenhouse["description"] == "Junior & SQL" and greenhouse["location"] == "Brussels, Belgium"
    lever = boards.fetch_company_board("lever", "acme")[0]
    assert "Python" in lever["description"] and lever["created"].startswith("2026-10-19")

    _settings, ctx = discovery.run_scope(agent_settings.load(), ["DE"], ["Data Analyst"])
    german = boards.fetch_arbeitsagentur("data analyst", ctx, ctx.regions[0])[0]
    assert german["location"] == "Rostock, Germany"
    assert german["description"] == "Einstieg für Berufsanfänger"
    assert german["url"].endswith("/jobdetail/123-ABC")

    remote = boards.fetch_remotive()[0]
    assert remote["location"] == "Remote · Europe" and remote["description"] == "Hi"


def test_company_boards_are_planned_from_settings():
    import discovery
    from job_sources import boards

    settings = {**agent_settings.load(), "company_boards": ["greenhouse:collibra", "recruitee:bunq", "bad"]}
    _settings, ctx = discovery.run_scope(settings, ["BE"])
    assert [s.label for s in boards.plan("company_boards", ctx)] == ["collibra (greenhouse)", "bunq (recruitee)"]
    assert boards.plan("jobtech", ctx) == []  # Sweden is not selected


def test_run_scope_regions_replace_allowed_locations():
    import discovery

    defaults = agent_settings.load()
    settings, ctx = discovery.run_scope(defaults, ["DE", "REMOTE"], ["Data Analyst", "Product Owner"])
    assert "berlin" in settings["allowed_locations"] and "antwerp" not in settings["allowed_locations"]
    assert "germany" not in settings["blocked_locations"] and "london" in settings["blocked_locations"]
    assert settings["target_roles"]["Product Owner"] == ["product owner"]
    assert ctx.role_queries["Product Owner"] == ["Product Owner"]
    assert ctx.wants_remote and [r["id"] for r in ctx.countries] == ["DE"]

    implicit, _ctx = discovery.run_scope(defaults)
    assert set(defaults["allowed_locations"]) <= set(implicit["allowed_locations"])


def test_catalog_lists_regions_roles_and_sources(client):
    body = client.get("/api/search/catalog").json()
    assert {"BE", "DE", "US", "REMOTE"} <= {region["id"] for region in body["regions"]}
    roles = {role["name"]: role for role in body["roles"]}
    assert roles["Data Analyst"]["has_profile"] and roles["Data Analyst"]["focus"]
    sources = {source["key"]: source for source in body["sources"]}
    assert sources["adzuna"]["configured"] is False  # no keys in the test environment
    assert sources["arbeitsagentur"]["regions"] == ["DE"]
    assert "REMOTE" not in sources["indeed"]["regions"]
    assert body["defaults"]["regions"] == ["BE", "NL"]


def test_search_settings_validate_regions_and_company_boards(client):
    settings = client.get("/api/settings/search").json()["settings"]
    ok = client.put("/api/settings/search", json={"settings": {
        **settings, "regions": ["de", "remote"], "company_boards": ["Greenhouse:collibra"]}})
    assert ok.status_code == 200
    assert ok.json()["settings"]["regions"] == ["DE", "REMOTE"]
    assert ok.json()["settings"]["company_boards"] == ["greenhouse:collibra"]
    assert client.put("/api/settings/search", json={"settings": {**settings, "regions": ["XX"]}}).status_code == 422
    bad_board = {**settings, "company_boards": ["workday:acme"]}
    assert client.put("/api/settings/search", json={"settings": bad_board}).status_code == 422


def test_jobs_outside_the_default_locations_survive_later_saves(project_root):
    import sqlite3
    from contextlib import closing

    import config
    import discovery

    settings, _ctx = discovery.run_scope(agent_settings.load(), ["DE", "REMOTE"], ["Data Analyst"])
    junior = {"description": "Junior role", "url": "u"}
    discovery.save_jobs_to_db([{**junior, "title": "Junior Data Analyst", "company_name": "Berlin GmbH",
                                "location": "Berlin, Germany"}], "Indeed", settings)
    discovery.save_jobs_to_db([{**junior, "title": "Junior BI Analyst", "company_name": "Remote Co",
                                "location": "Remote · Worldwide"}], "Jobicy", settings)
    discovery.save_jobs_to_db([], "Gmail", settings)  # every save runs init_db again
    with closing(sqlite3.connect(config.DB_PATH)) as conn:
        locations = {row[0] for row in conn.execute("SELECT location FROM jobs")}
    assert locations == {"Berlin, Germany", "Remote · Worldwide"}


def test_role_family_falls_back_to_the_description(project_root):
    import sqlite3
    from contextlib import closing

    import config
    import discovery

    settings, _ctx = discovery.run_scope(agent_settings.load(), ["BE"], ["Data Analyst", "Data Engineer"])
    discovery.save_jobs_to_db([
        {"title": "Junior Data Insights Specialist", "company_name": "KPMG", "location": "Zaventem, Belgium",
         "description": "You join our business intelligence team building Power BI reports."},
        {"title": "Junior Data Engineer", "company_name": "Acme", "location": "Ghent, Belgium",
         "description": "Pipelines that feed business intelligence dashboards."},
    ], "LinkedIn", settings)
    with closing(sqlite3.connect(config.DB_PATH)) as conn:
        families = dict(conn.execute("SELECT title, role_family FROM jobs"))
    assert families == {"Junior Data Insights Specialist": "Data Analyst", "Junior Data Engineer": "Data Engineer"}
