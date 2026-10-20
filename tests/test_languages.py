"""The job-language filter: required languages, the posting's own language and the run option."""
from helpers import fake_scrape, install_fakes

import languages


def test_required_languages_must_all_be_picked():
    english_only = "We are hiring a data engineer. You are fluent in English. Dutch or French is a plus."
    assert languages.required_languages(english_only) == [{"en"}]
    assert languages.check_job("Data Engineer", english_only, ["en"]) == (True, "")

    keep, reason = languages.check_job("Data Engineer", "You speak fluent Dutch and English.", ["en"])
    assert not keep and "Dutch" in reason
    assert languages.check_job("Data Engineer", "You speak fluent Dutch and English.", ["en", "nl"])[0]


def test_a_choice_between_languages_needs_only_one():
    text = "Languages: Dutch or French, and English."
    assert languages.required_languages(text) == [{"nl", "fr"}, {"en"}]
    assert languages.check_job("Analyst", text, ["en", "nl"])[0]
    assert not languages.check_job("Analyst", text, ["en"])[0]


def test_speaker_words_count_as_requirements():
    assert languages.required_languages("Looking for a Dutch-speaking analyst to join us.") == [{"nl"}]
    assert languages.required_languages("Je bent Nederlandstalig.") == [{"nl"}]
    assert languages.required_languages("Du hast sehr gute Deutschkenntnisse.") == [{"de"}]
    # A nationality in passing is not a requirement.
    assert languages.required_languages("Our German office works with clients across Europe.") == []


def test_without_a_requirement_the_posting_language_decides():
    dutch = "Voor onze klant in Brugge zoeken we een Data Analist. Je werkt nauw samen met de teams om data te analyseren."
    keep, reason = languages.check_job("Data Analist", dutch, ["en"])
    assert not keep and reason.startswith("Posted in Dutch")
    assert languages.check_job("Data Analist", dutch, ["nl"])[0]
    english = "Agoya is a data and AI agency with a mission: to help clients activate their data and grow."
    assert languages.check_job("Data Engineer", english, ["en"])[0]
    # A Dutch post that explicitly asks for English is kept for English.
    assert languages.check_job("Data Analist", dutch + " Vloeiend Engels is vereist.", ["en"])[0]


def test_too_little_text_or_no_pick_keeps_the_job():
    assert languages.detect_language("Internship : Data analyst (H/F)") is None
    assert languages.check_job("Internship : Data analyst (H/F)", "", ["en"]) == (True, "")
    assert languages.check_job("Data Analist", "Je spreekt vloeiend Nederlands.", []) == (True, "")


def test_html_descriptions_are_read_as_text():
    html = "<p><strong>Ben jij</strong> een data analist?</p><p>Je werkt met onze klanten en het team aan rapporten voor de business.</p>"
    assert languages.detect_language(html) == "nl"


def test_a_run_keeps_only_jobs_in_the_picked_languages(monkeypatch):
    import main
    from job_sources import scrapers

    def german_scrape(**kwargs):
        rows = fake_scrape(**kwargs)
        rows[0]["description"] = ("Wir suchen dich als Junior Data Analyst. Du hast sehr gute Deutschkenntnisse "
                                  "und Erfahrung mit SQL und Python in einem Team.")
        return rows

    install_fakes(monkeypatch)
    monkeypatch.setattr(scrapers, "_scrape", german_scrape)
    options = {"regions": ["DE"], "roles": ["Data Analyst"], "dry_run": True, "sources": ["linkedin"]}

    english = main.run_agent(interactive=False, options={**options, "languages": ["en"]})
    assert english["eligible"] == 0 and english["language_filtered"] == 1
    german = main.run_agent(interactive=False, options={**options, "languages": ["de"]})
    assert german["eligible"] == 1 and german["language_filtered"] == 0
    anything = main.run_agent(interactive=False, options={**options, "languages": []})
    assert anything["eligible"] == 1


def test_run_options_and_settings_validate_languages(client):
    assert client.post("/api/search/plan", json={"languages": ["xx"]}).status_code == 422
    catalog = client.get("/api/search/catalog").json()
    assert {"en", "nl", "fr", "de"} <= {language["id"] for language in catalog["languages"]}
    assert catalog["defaults"]["languages"] == ["en"]
    settings = client.get("/api/settings/search").json()["settings"]
    ok = client.put("/api/settings/search", json={"settings": {**settings, "languages": ["EN", "nl"]}})
    assert ok.status_code == 200 and ok.json()["settings"]["languages"] == ["en", "nl"]
    assert client.put("/api/settings/search", json={"settings": {**settings, "languages": ["xx"]}}).status_code == 422
