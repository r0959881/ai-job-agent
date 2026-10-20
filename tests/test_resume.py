"""Resume API: validation round-trip, backups, raw YAML and previews."""
import copy

import yaml
from helpers import resume_text, set_resume_text


def get(client):
    response = client.get("/api/resume")
    assert response.status_code == 200, response.text
    return response.json()


def test_get_returns_the_yaml_structure(client):
    body = get(client)
    data = body["data"]
    assert data["personal_info"]["full_name"] == "Ammar Haider"
    assert list(data) == ["personal_info", "role_profiles", "standard_answers", "core_skills", "experience",
                          "projects", "certifications", "education", "languages"]
    assert body["warnings"] == [] and body["empty"] is False


def test_save_without_changes_is_byte_identical_and_makes_no_backup(client):
    before = resume_text()
    body = get(client)
    response = client.put("/api/resume", json={"data": body["data"], "etag": body["etag"]})
    assert response.status_code == 200
    assert response.json()["backup_id"] is None
    assert resume_text() == before


def test_edits_round_trip_through_the_cli_reader(client, project_root):
    body = get(client)
    data = copy.deepcopy(body["data"])
    data["experience"].insert(0, {"company": "NewCo", "role": "Data Engineer", "location": "Gent", "dates": "2027",
                                  "type": "", "bullets": ["Built things"]})
    data["experience"][1]["bullets"].reverse()
    data["core_skills"]["cloud_extra"] = ["GCP"]
    data["projects"] = data["projects"][::-1]
    data["role_profiles"]["Data Engineer"]["keywords"].append("dbt")
    response = client.put("/api/resume", json={"data": data, "etag": body["etag"]})
    assert response.status_code == 200, response.text
    assert response.json()["backup_id"]

    text = resume_text()
    on_disk = yaml.safe_load(text)
    assert on_disk["experience"][0]["company"] == "NewCo"
    assert on_disk["core_skills"]["cloud_extra"] == ["GCP"]
    assert on_disk["projects"][0]["title"] == data["projects"][0]["title"]
    assert '    keywords: ["data engineering"' in text  # flow style kept for untouched lists' siblings

    from generate_doc import create_tailored_cv_docx

    path = create_tailored_cv_docx("Acme", "Data Engineer", "Summary.", ["One"], "Data Engineer")
    assert (project_root / path).exists()


def test_invalid_data_returns_field_errors_and_writes_nothing(client):
    before = resume_text()
    data = get(client)["data"]
    data["experience"][0]["company"] = ""
    data["personal_info"]["email"] = "not-an-email"
    response = client.put("/api/resume", json={"data": data})
    assert response.status_code == 422
    errors = response.json()["detail"]["errors"]
    locs = {".".join(e["loc"]) for e in errors}
    assert {"experience.0.company", "personal_info.email"} <= locs
    assert any(e["msg"] == "This field is required." for e in errors)
    assert resume_text() == before


def test_stale_etag_is_rejected(client):
    body = get(client)
    set_resume_text(resume_text() + "\n# edited elsewhere\n")
    response = client.put("/api/resume", json={"data": body["data"], "etag": body["etag"]})
    assert response.status_code == 409


def test_backups_are_listed_restorable_and_capped(client):
    from api.services import resume_store

    original = resume_text()
    data = get(client)["data"]
    for index in range(23):
        data["personal_info"]["headline"] = f"Headline {index}"
        assert client.put("/api/resume", json={"data": data}).status_code == 200
    backups = client.get("/api/resume/backups").json()
    assert len(backups) == resume_store.KEEP_BACKUPS
    assert backups[0]["created_at"] > backups[-1]["created_at"]

    first = backups[-1]["id"]
    text = client.get(f"/api/resume/backups/{first}").json()["text"]
    assert "Headline 2" in text
    restored = client.post(f"/api/resume/backups/{first}/restore")
    assert restored.status_code == 200
    assert restored.json()["data"]["personal_info"]["headline"] == "Headline 2"
    assert original != resume_text()


def test_backup_ids_cannot_escape_the_backup_folder(client):
    assert client.get("/api/resume/backups/..%2F..%2Fjobs").status_code == 404
    assert client.post("/api/resume/backups/../../etc/restore").status_code in {404, 405}


def test_raw_yaml_errors_have_line_numbers(client):
    text = client.get("/api/resume/raw").json()["text"]
    broken = text.replace('company: "Estée Lauder Companies"\n', 'company: ""\n', 1)
    result = client.post("/api/resume/raw/validate", json={"text": broken}).json()
    assert not result["valid"]
    line = result["errors"][0]["line"]
    assert broken.splitlines()[line - 1].strip().startswith("- company")

    syntax = client.post("/api/resume/raw/validate", json={"text": "personal_info:\n  full_name: [unclosed\n"}).json()
    assert syntax["errors"][0]["line"] >= 2 and "YAML syntax error" in syntax["errors"][0]["message"]

    assert client.put("/api/resume/raw", json={"text": broken}).status_code == 422


def test_raw_save_keeps_comments(client):
    text = "# my comment\n" + client.get("/api/resume/raw").json()["text"]
    assert client.put("/api/resume/raw", json={"text": text}).status_code == 200
    body = get(client)
    data = body["data"]
    data["languages"].append("French: A1")
    assert client.put("/api/resume", json={"data": data, "etag": body["etag"]}).status_code == 200
    saved = resume_text()
    assert saved.startswith("# my comment\n") and '"French: A1"' in saved


def test_missing_resume_is_empty_not_an_error(client):
    set_resume_text("")
    body = get(client)
    assert body["empty"] is True
    assert body["data"]["experience"] == []


def test_preview_renders_unsaved_data(client):
    data = get(client)["data"]
    data["personal_info"]["full_name"] = "Preview Person"
    response = client.post("/api/resume/preview", json={"data": data, "role_family": "Data Analyst"})
    assert response.status_code == 200
    html = response.json()["html"]
    assert "PREVIEW PERSON" in html and "<script" not in html


def test_role_profile_warnings(client):
    data = get(client)["data"]
    data["projects"] = data["projects"][1:]
    assert client.put("/api/resume", json={"data": data}).status_code == 200
    warnings = get(client)["warnings"]
    assert any("Refrigerator Ships Production ETL Pipeline" in w for w in warnings)
