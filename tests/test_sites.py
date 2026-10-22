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
    assert job["location"] == "Antwerpen, Belgium" and "Kennis van SQL" in job["description"]
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


POSTING = {"@type": "JobPosting", "title": "Junior Data Analyst", "datePosted": TODAY, "employmentType": ["FULL_TIME"],
           "description": "<p>Build Power BI reports.</p>", "hiringOrganization": {"name": "Randstad"},
           "jobLocation": {"address": {"addressLocality": "Mechelen", "addressRegion": "Antwerpen"}}}


def test_randstad_takes_recent_jobs_from_its_sitemap(monkeypatch):
    no_pause(monkeypatch)
    base = "https://www.randstad.be/werknemers/jobs"
    titled = f"{base}/junior-data-analyst_mechelen_2f7b726d-3e05-4087-aeaf-c358587c7c63/"
    listed = f"{base}/reporting-specialist_gent_11111111-3e05-4087-aeaf-c358587c7c63/"
    old = f"{base}/data-analyst_brugge_22222222-3e05-4087-aeaf-c358587c7c63/"
    closed = f"{base}/data-analyst-bi_ghent_33333333-3e05-4087-aeaf-c358587c7c63/"
    now = datetime.now(UTC).isoformat()
    sitemap = "".join(f"<url><loc>{url}</loc><lastmod>{modified}</lastmod></url>"
                      for url, modified in ((titled, now), (listed, now), (old, "2020-01-01T00:00:00+00:00"),
                                            (closed, now)))
    posting = lambda title: f'<script type="application/ld+json">{json.dumps({**POSTING, "title": title})}</script>'
    pages = {
        **{url: sitemap for url in sites.RANDSTAD_SITEMAPS},
        f"{base}/q-data-analyst/": f'<a href="{listed[len("https://www.randstad.be"):]}">x</a>'
                                   f'<a href="{old[len("https://www.randstad.be"):]}">x</a>',
        titled: posting("Junior Data Analyst"), listed: posting("Reporting Specialist"),
        closed: "<main><h1>Helaas, deze vacature is afgesloten</h1></main>",
    }
    monkeypatch.setattr(sites, "_randstad_sitemap", {"at": 0.0, "jobs": {}})
    monkeypatch.setattr(sites, "_get", lambda url, params=None, browser=False: pages[url])

    jobs = sites.fetch_randstad("data analyst", context(), context().regions[0], sites.DetailCache())
    # Listed by the search and recent, or recent with the words in its title; not the old one, not the closed one
    assert sorted(job["title"] for job in jobs) == ["Junior Data Analyst", "Reporting Specialist"]
    job = next(job for job in jobs if job["title"] == "Junior Data Analyst")
    assert job["location"] == "Mechelen, Antwerpen, Belgium" and job["description"] == "Build Power BI reports."
    assert job["created"] == TODAY and job["contract_type"] == "FULL_TIME"


def test_robert_half_reads_the_job_list_embedded_in_its_page(monkeypatch):
    found = {"found": "2", "jobs": [
        {"jobtitle": "Data Analyst", "city": "Wommelgem", "date_posted": "2026-10-20T13:33:56Z", "emptype": "Perm",
         "description": '<p>Report in <a href="https://x.example/y">Power BI</a>.</p>',
         "job_detail_url": "https://www.roberthalf.com/be/nl/vacature/wommelgem-antwerp/data-analyst/000515641-benl"},
        {"jobtitle": "Senior Data Analyst", "city": "Ghent", "date_posted": "2026-10-21T08:00:00Z"},
    ]}
    # The page carries it as a JavaScript string: quotes as \x22, slashes as \/, dashes as \u002D
    escaped = (json.dumps(found, separators=(",", ":")).replace("\\", "\\\\").replace('"', "\\x22").replace("/", "\\/")
               .replace("-", "\\u002D"))
    page = f"<script>window.searchResult = JSON.parse('{escaped}');</script>"
    monkeypatch.setattr(sites, "_get", lambda url, params=None, browser=False: page)

    jobs = sites.fetch_robert_half("data analyst", context(), context().regions[0])
    assert [job["title"] for job in jobs] == ["Data Analyst"]  # "Senior" is an excluded title word
    assert jobs[0]["location"] == "Wommelgem, Belgium" and jobs[0]["created"] == "2026-10-20T13:33:56Z"
    assert jobs[0]["description"] == "Report in Power BI ." and jobs[0]["url"].endswith("000515641-benl")

    # A search without results carries "found": "0" and no job list: no jobs, not an error
    empty = "<script>window.searchResult = JSON.parse('{\\x22found\\x22:\\x220\\x22,\\x22facets\\x22:{}}');</script>"
    monkeypatch.setattr(sites, "_get", lambda url, params=None, browser=False: empty)
    assert sites.fetch_robert_half("machine learning", context(), context().regions[0]) == []


def test_manpower_reads_newest_job_numbers_first_and_stops_at_old_postings(monkeypatch):
    no_pause(monkeypatch)
    numbers = [100, 300, 200, 400, 250]  # the order the site lists them in (by relevance)
    dates = {400: TODAY, 300: "2020-01-01", 250: "2020-01-01", 200: "2020-01-01", 100: TODAY}
    opened = []

    def fake_get(url, params=None, browser=False):
        if params:  # a result page; the second one is empty
            return "".join(f'<a href="/nl/vacature/data-analyst-{n}">x</a>' for n in numbers) if params["page"] == 1 else ""
        opened.append(int(url.rsplit("-", 1)[1]))
        number = opened[-1]
        return f'<script type="application/ld+json">{json.dumps({**POSTING, "datePosted": dates[number]})}</script>'

    monkeypatch.setattr(sites, "_get", fake_get)
    jobs = sites.fetch_manpower("data analyst", context(), context().regions[0], sites.DetailCache())
    assert opened == [400, 300, 250, 200]  # newest first; three old ones in a row end it, so 100 is never opened
    assert [job["created"] for job in jobs][:1] == [TODAY]


def test_actiris_and_le_forem_read_their_search_services(monkeypatch):
    from curl_cffi import requests as browser_requests

    offers = {"offers": [{"reference": "5979763", "titreNl": "Data Analist M/V/X", "codePostal": "1070",
                          "communeNl": "Anderlecht", "typeContratLibelle": "Onbepaalde duur",
                          "typeOffer": "DirectOnline", "dateCreation": f"{TODAY}T13:23:36+02:00"}]}
    monkeypatch.setattr(browser_requests, "post", lambda url, json=None, **_k: FakeResponse(offers))
    job = sites.fetch_actiris("data analyst", context(), context().regions[0])[0]
    assert job["title"] == "Data Analist M/V/X" and job["location"] == "1070 Anderlecht, Belgium"
    assert job["url"].endswith("jobadvertentie/?reference=5979763&type=DirectOnline")

    records = {"results": [{"titreoffre": "Analyste de données (H/F/X)", "nomemployeur": "ACME",
                            "lieuxtravaillocalite": ["NAMUR"], "typecontrat": "CDI", "langues": ["Français"],
                            "url": "https://www.leforem.be/recherche-offres/offre-detail/1", "datedebutdiffusion": TODAY}]}
    asked = []
    monkeypatch.setattr(sites, "_forem_feeds", {})
    monkeypatch.setattr(sites.requests, "get", lambda url, params=None, **_k: asked.append(params) or FakeResponse(records))
    job = sites.fetch_forem("data analyst", context(), context().regions[0])[0]
    assert 'search("data analyst")' in asked[0]["where"] and job["company_name"] == "ACME"
    assert job["location"] == "NAMUR, Belgium" and "Required languages: Français" in job["description"]


def test_le_forem_is_asked_once_per_run_and_retried_when_rate_limited(monkeypatch):
    records = {"results": [{"titreoffre": "Data Analyst", "nomemployeur": "A", "datedebutdiffusion": TODAY},
                           {"titreoffre": "Business Intelligence Developer", "nomemployeur": "B",
                            "datedebutdiffusion": TODAY}]}
    answers = [FakeResponse({}, status=429), FakeResponse(records)]
    asked = []

    def fake_get(url, params=None, **_kwargs):
        asked.append(params)
        response = answers.pop(0)
        response.headers = {"Retry-After": "0"}
        return response

    monkeypatch.setattr(sites, "_forem_feeds", {})
    monkeypatch.setattr(sites.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(sites.requests, "get", fake_get)
    ctx = context()  # phrases: "data analyst", "business intelligence"

    analysts = sites.fetch_forem("data analyst", ctx, ctx.regions[0])
    bi = sites.fetch_forem("business intelligence", ctx, ctx.regions[0])
    assert len(asked) == 2  # the 429, then its retry; the second search reuses the feed
    assert 'search("data analyst") OR search("business intelligence")' in asked[0]["where"]
    assert [job["company_name"] for job in analysts] == ["A"] and [job["company_name"] for job in bi] == ["B"]


def test_le_forem_stops_asking_once_its_daily_quota_is_spent(monkeypatch):
    import pytest

    quota = FakeResponse({"error": "You have exceeded the requests limit for anonymous users.",
                          "reset_time": "2999-01-01T00:00:00Z", "call_limit": 10000}, status=429)
    asked = []
    monkeypatch.setattr(sites, "_forem_feeds", {})
    monkeypatch.setattr(sites, "_forem_quota", {"reset": None})
    monkeypatch.setattr(sites.requests, "get", lambda url, params=None, **_k: asked.append(params) or quota)
    ctx = context()

    for _ in range(3):
        with pytest.raises(sites.ForemQuotaReached, match="limit is reached"):
            sites.fetch_forem("data analyst", ctx, ctx.regions[0])
    assert len(asked) == 1  # no retries, and no new request until the quota resets
