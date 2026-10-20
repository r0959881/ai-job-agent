"""StepStone, VDAB, Michael Page and Jobat adapters, parsed from trimmed copies of their real pages."""
import json
from datetime import UTC, date, datetime

from helpers import FakeResponse

import agent_settings
import discovery
import job_sources
import languages
from job_sources import sites

TODAY = datetime.now(UTC).date().isoformat()


def context(regions=("BE",), window_hours=168):
    settings, ctx = discovery.run_scope(agent_settings.load(), list(regions), ["Data Analyst"], window_hours)
    return ctx


def no_pause(monkeypatch):
    monkeypatch.setattr(sites, "DETAIL_PAUSE", 0)


def test_stepstone_reads_the_embedded_result_list(monkeypatch):
    state = {"searchResults": {"items": [{
        "title": "Junior Data Analyst", "companyName": "La Lorraine", "location": "Ninove",
        "url": "https://www.stepstone.be/jobs--Junior-Data-Analyst--1-inline.html?rltr=1",
        "datePosted": f"{TODAY}T08:00:00Z", "textSnippet": "As a junior data analyst you build Power BI reports.",
        "jobBenefitsHtml": "<ul><li>Meal vouchers</li></ul>",
    }]}}
    page = f'<script>window.__PRELOADED_STATE__["app-unifiedResultlist"] = {json.dumps(state)};\n</script>'
    calls = []
    monkeypatch.setattr(sites, "_get", lambda url, params=None, browser=False: calls.append((url, params)) or page)

    job = sites.fetch_stepstone("data analyst", context(), context().regions[0])[0]
    assert calls[0] == ("https://www.stepstone.be/jobs/data-analyst", {"ag": "age_7", "sort": 2})
    assert job["url"] == "https://www.stepstone.be/jobs--Junior-Data-Analyst--1-inline.html"
    assert job["location"] == "Ninove, Belgium" and "Power BI" in job["description"] and "Meal" in job["description"]


def test_vdab_adds_required_languages_and_experience(monkeypatch):
    no_pause(monkeypatch)
    found = {"resultaten": [{
        "id": {"id": 7430}, "vacaturefunctie": {"naam": "Data Analist"}, "vacatureBedrijfsnaam": "Digipolis",
        "tewerkstellingsLocatieRegioOfAdres": "ANTWERPEN", "eerstePublicatieDatum": f"{TODAY}T11:00:00Z",
        "ervaring": "Geen ervaring",
    }]}
    detail = {"functie": {"omschrijving": {"html": "<p>Je bouwt rapporten in Power BI.</p>"}},
              "profiel": {"vereisteKwalificaties": {"html": "<ul><li>Kennis van SQL</li></ul>"},
                          "talenKennis": [{"taalCode": {"label": "Nederlands"}, "scoreCode": {"kortLabel": "Zeer goed"}}],
                          "beroepCompetenties": [{"werkervaring": {"code": "1"}}]}}
    posted = []
    monkeypatch.setattr(sites.requests, "post", lambda url, data=None, **_k: posted.append(json.loads(data))
                        or FakeResponse(found))
    monkeypatch.setattr(sites.requests, "get", lambda url, **_k: FakeResponse(detail))

    job = sites.fetch_vdab("data analyst", context(window_hours=48), context().regions[0], sites.DetailCache())[0]
    assert posted[0]["criteria"] == {"trefwoord": "data analyst", "sorteerVeld": "DATUM", "onlineSindsCode": "1"}
    assert job["url"] == "https://www.vdab.be/vindeenjob/vacatures/7430"
    assert job["location"] == "Antwerpen" and "Kennis van SQL" in job["description"]
    assert "Required languages: Nederlands (Zeer goed)" in job["description"]
    assert "Seniority level: entry level" in job["description"]
    assert languages.required_languages(job["description"]) == [{"nl"}]


def test_michael_page_skips_suggestions_and_reads_details(monkeypatch):
    no_pause(monkeypatch)
    listing = """
      <div class="job-tile"><div class="job-title"><h3><a href="/job-detail/data-analyst/ref/jn-1">Data Analyst</a>
      </h3></div><div class="job-location"> Zaventem</div><div class="job-summary"><p>Reporting role.</p></div></div>
      <div class="job-tile"><div class="job-title"><h3>
      <a href="/job-detail/office-coordinator/ref/jn-2?ng-src=other-users-applied">Office Coordinator</a></h3></div></div>
    """
    posting = {"@type": "JobPosting", "description": "<p>Junior data analyst, SQL and Power BI.</p>",
               "datePosted": TODAY, "hiringOrganization": {"name": "Michael Page BeLux"},
               "jobLocation": {"address": {"addressLocality": "Zaventem", "addressRegion": "Belgium"}}}
    pages = {"https://www.michaelpage.be/jobs/data-analyst": listing,
             "https://www.michaelpage.be/job-detail/data-analyst/ref/jn-1":
                 f'<script type="application/ld+json">{json.dumps(posting)}</script>'}
    monkeypatch.setattr(sites, "_get", lambda url, params=None, browser=False: pages[url])

    jobs = sites.fetch_michael_page("data analyst", context(), context().regions[0], sites.DetailCache())
    assert [job["title"] for job in jobs] == ["Data Analyst"]
    assert jobs[0]["created"] == TODAY and jobs[0]["location"] == "Zaventem, Belgium"
    assert "Power BI" in jobs[0]["description"] and jobs[0]["company_name"] == "Michael Page BeLux"


def test_michael_page_without_results_is_empty_not_an_error(monkeypatch):
    import requests

    def not_found(url, params=None, browser=False):
        response = requests.Response()
        response.status_code = 404
        raise requests.HTTPError("404", response=response)

    monkeypatch.setattr(sites, "_get", not_found)
    assert sites.fetch_michael_page("data platform", context(), context().regions[0], sites.DetailCache()) == []


def test_jobat_stops_at_old_results_and_skips_excluded_details(monkeypatch):
    no_pause(monkeypatch)

    def card(job_id, title, age):
        return f"""<div class="jobResults-card"><h2 class="jobTitle"><a href="/nl/jobs/x/job_{job_id}">{title}</a></h2>
          <li class="jobCard-company">Acme</li><li class="jobCard-location">Gent</li>
          <span class="jobCard-duration">{age}</span></div>"""

    listing = card(1, "Junior Data Analist", "Sinds vandaag") + card(2, "Senior Data Analist", "Sinds 1 dag") \
        + card(3, "Data Analist", "Sinds 3 weken")
    detail = """<div id="jobdetail"><meta itemprop="datePosted" content="2026-10-20" />
      <meta itemprop="description" content="Je analyseert data met SQL." />
      <div itemprop="qualifications">Vloeiend Nederlands</div><span itemprop="addressLocality">Gent</span></div>"""
    fetched = []

    def fake_get(url, params=None, browser=False):
        fetched.append((url, browser))
        return listing if "/results/" in url else detail

    monkeypatch.setattr(sites, "_get", fake_get)
    jobs = sites.fetch_jobat("data analyst", context(window_hours=48), context().regions[0], sites.DetailCache())

    assert [job["title"] for job in jobs] == ["Junior Data Analist", "Senior Data Analist"]
    assert all(browser for _url, browser in fetched)  # Jobat needs the browser fingerprint
    assert [url for url, _ in fetched].count("https://www.jobat.be/nl/jobs/x/job_1") == 1
    assert "https://www.jobat.be/nl/jobs/x/job_2" not in [url for url, _ in fetched]  # "senior" is excluded
    assert jobs[0]["description"] == "Je analyseert data met SQL.\n\nVloeiend Nederlands"


def test_jobat_relative_dates():
    today = date(2026, 10, 20)
    assert sites.jobat_posted("Sinds vandaag", today) == "2026-10-20"
    assert sites.jobat_posted("Sinds 1 dag", today) == "2026-10-19"
    assert sites.jobat_posted("Sinds 2 weken", today) == "2026-10-06"
    assert sites.jobat_posted("", today) == ""


def test_sites_cover_their_countries():
    ctx = context(regions=("BE", "LU", "DE", "NL"))
    by_source = {key: {search.region["id"] for search in job_sources.plan(key, ctx)}
                 for key in ("stepstone", "vdab", "michaelpage", "jobat")}
    assert by_source == {"stepstone": {"BE", "DE"}, "vdab": {"BE"}, "michaelpage": {"BE", "DE"}, "jobat": {"BE"}}
    # One search per phrase: Belgium and Luxembourg share michaelpage.be.
    assert len(job_sources.plan("michaelpage", ctx)) == 2 * len(ctx.queries())
    assert job_sources.plan("jobat", context(regions=("FR",))) == []


def test_new_sources_are_in_the_catalog_and_settings(client):
    sources = {source["key"]: source for source in client.get("/api/search/catalog").json()["sources"]}
    assert sources["vdab"]["kind"] == "api" and sources["vdab"]["regions"] == ["BE"]
    assert sources["jobat"]["kind"] == "scraper" and sources["stepstone"]["regions"] == ["BE", "DE"]
    assert "LU" in sources["michaelpage"]["regions"]
    settings = client.get("/api/settings/search").json()["settings"]
    assert all(settings["sources"][key] for key in ("stepstone", "vdab", "michaelpage", "jobat"))
