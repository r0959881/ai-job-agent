"""Jobs grid, Apply workspace actions and the documents library."""
from datetime import UTC, datetime, timedelta

import pytest
from helpers import FakeGroq

import config
from database import init_db, record_document, transaction


def add_job(job_id, title, company="Acme", location="Antwerp, Belgium", source="Adzuna Belgium", **extra):
    fields = {"id": job_id, "title": title, "company": company, "location": location, "url": f"https://example.com/{job_id}",
              "source": source, "description": extra.pop("description", f"{title} with SQL and Power BI"),
              "discovered_at": extra.pop("discovered_at", datetime.now(UTC).isoformat()), **extra}
    with transaction() as conn:
        conn.execute(f"INSERT INTO jobs ({', '.join(fields)}) VALUES ({', '.join('?' for _ in fields)})",
                     tuple(fields.values()))


@pytest.fixture
def jobs(project_root):
    init_db()
    old = (datetime.now(UTC) - timedelta(days=10)).isoformat()
    add_job("a", "Junior Data Analyst", role_family="Data Analyst", salary_max=4000)
    add_job("b", "Junior Data Engineer", company="Beta", role_family="Data Engineer", discovered_at=old,
            source="LinkedIn Alerts", status="processed", cv_path="output/b.docx")
    add_job("c", "Data Scientist Intern", company="Gamma", role_family="Data Science", application_status="applied",
            applied_at=datetime.now(UTC).isoformat())
    (project_root / "output" / "b.docx").write_bytes(b"x")
    return ["a", "b", "c"]


def ids(response):
    assert response.status_code == 200, response.text
    return [job["id"] for job in response.json()["items"]]


def test_filters_search_sort_and_paging(client, jobs):
    assert set(ids(client.get("/api/jobs"))) == {"a", "b", "c"}
    assert ids(client.get("/api/jobs?q=engineer")) == ["b"]
    assert ids(client.get("/api/jobs?role_family=Data Analyst&role_family=Data Science&sort=title&order=asc")) == ["c", "a"]
    assert ids(client.get("/api/jobs?source=LinkedIn")) == ["b"]
    assert ids(client.get("/api/jobs?has_cv=true")) == ["b"]
    assert ids(client.get("/api/jobs?quick=ready")) == ["b"]
    assert ids(client.get("/api/jobs?quick=applied_week")) == ["c"]
    since = (datetime.now(UTC) - timedelta(days=2)).date().isoformat()
    assert set(ids(client.get(f"/api/jobs?date_from={since}"))) == {"a", "c"}
    assert ids(client.get("/api/jobs?sort=salary&order=desc"))[0] == "a"
    page = client.get("/api/jobs?page_size=2&page=2&sort=title&order=asc").json()
    assert page["total"] == 3 and len(page["items"]) == 1
    facets = client.get("/api/jobs").json()["facets"]
    assert "LinkedIn Alerts" in facets["sources"] and "Data Engineer" in facets["role_families"]


def test_detail_has_keywords_and_source_tips(client, jobs):
    job = client.get("/api/jobs/b").json()
    assert job["has_cv"] and job["cv_path"] == "output/b.docx"
    assert "SQL" in job["matched_keywords"]
    assert any("Easy Apply" in tip for tip in job["tips"])
    assert job["history"][0]["text"].startswith("Found via")
    assert client.get("/api/jobs/missing").status_code == 404


def test_tracking_status_dates_notes_and_checklist(client, jobs):
    job = client.patch("/api/jobs/a", json={"application_status": "applied", "notes": "Sent via site",
                                            "apply_checklist": {"review": True, "bogus": True}}).json()
    assert job["application_status"] == "applied" and job["applied_at"]
    assert job["notes"] == "Sent via site" and job["apply_checklist"] == {"review": True}
    job = client.patch("/api/jobs/a", json={"follow_up_at": "2026-11-01"}).json()
    assert job["follow_up_at"] == "2026-11-01"
    assert client.patch("/api/jobs/a", json={"application_status": "ghosted"}).status_code == 422


def test_tailor_with_edited_content_and_cover_letter(client, jobs, monkeypatch, project_root):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    import tailor

    monkeypatch.setattr(tailor, "get_client", lambda: FakeGroq())
    preview = client.post("/api/jobs/a/tailor/preview").json()
    assert preview["summary"] == "Tailored summary." and preview["bullets"] == ["Bullet one", "Bullet two"]

    result = client.post("/api/jobs/a/tailor", json={"summary": "My own summary.", "bullets": ["Edited bullet"]}).json()
    assert (project_root / result["path"]).exists()
    detail = result["job"]
    assert detail["status"] == "processed" and detail["has_cv"]
    html = client.get(f"/api/documents/{detail['documents'][0]['id']}/preview").json()["html"]
    assert "My own summary." in html and "Edited bullet" in html

    letter = client.post("/api/jobs/a/cover-letter", json={}).json()
    assert "Cover_Letter_Acme_Junior Data Analyst" in letter["path"]
    assert letter["job"]["cover_letter_path"] == letter["path"]
    kinds = sorted(d["kind"] for d in letter["job"]["documents"])
    assert kinds == ["cover_letter", "cv"]


def test_tailoring_without_a_key_explains_how_to_fix_it(client, jobs):
    response = client.post("/api/jobs/a/tailor")
    assert response.status_code == 400 and "Settings → Integrations" in response.json()["detail"]


def test_partner_companies_are_not_used_in_cover_letters(client, jobs):
    add_job("p", "Junior Data Analyst", company="Partner (LinkedIn Alerts)", source="LinkedIn Alerts")
    path = client.post("/api/jobs/p/cover-letter", json={}).json()["path"]
    assert "Partner" not in path
    path = client.post("/api/jobs/p/cover-letter", json={"company": "Real Co"}).json()["path"]
    assert "Real Co" in path


def test_delete_job_and_bulk_actions(client, jobs, project_root):
    record_document("output/b.docx", "cv", job_id="b")
    assert client.delete("/api/jobs/b?delete_files=true").status_code == 200
    assert not (project_root / "output" / "b.docx").exists()
    assert client.get("/api/jobs/b").status_code == 404

    result = client.post("/api/jobs/bulk", json={"ids": ["a", "c", "nope"], "action": "skip"}).json()
    assert result["done"] == ["a", "c"] and result["failed"][0]["id"] == "nope"
    assert client.get("/api/jobs/a").json()["application_status"] == "skipped"


def test_documents_list_preview_download_and_orphans(client, jobs, project_root):
    from generate_doc import create_tailored_cv_docx

    path = create_tailored_cv_docx("Acme", "Junior Data Analyst", "Summary.", ["One"], "Data Analyst")
    record_document(path, "cv", job_id="a")
    (project_root / "output" / "Ammar_Haider_CV_Sample_Data Analyst.docx").write_bytes(b"not a real docx")
    client.post("/api/documents/rescan")
    items = client.get("/api/documents").json()["items"]
    by_name = {d["name"]: d for d in items}
    cv = by_name["Ammar_Haider_CV_Acme_Junior Data Analyst.docx"]
    assert cv["job_title"] == "Junior Data Analyst" and cv["exists"]
    orphans = {d["name"] for d in client.get("/api/documents?orphans=true").json()["items"]}
    assert "Ammar_Haider_CV_Sample_Data Analyst.docx" in orphans and cv["name"] not in orphans

    download = client.get(f"/api/documents/{cv['id']}/download")
    assert download.status_code == 200 and download.content[:2] == b"PK"
    assert "SUMMARY" in client.get(f"/api/documents/{cv['id']}/preview").json()["html"].upper()

    assert client.delete(f"/api/documents/{cv['id']}").status_code == 200
    assert not (project_root / path).exists()
    assert client.get("/api/jobs/a").json()["cv_path"] == ""


def test_files_outside_output_are_never_served(client, project_root):
    init_db()
    secret = project_root / "secret.txt"
    secret.write_text("token")
    with transaction() as conn:
        conn.execute("INSERT INTO documents (kind, path) VALUES ('other', '../secret.txt')")
        conn.execute("INSERT INTO documents (kind, path) VALUES ('other', ?)", (str(secret),))
        conn.execute("INSERT INTO documents (kind, path) VALUES ('other', 'output/../.env')")
    for doc in client.get("/api/documents").json()["items"]:
        assert client.get(f"/api/documents/{doc['id']}/download").status_code == 403
        assert client.delete(f"/api/documents/{doc['id']}").status_code == 403
    assert secret.exists()


def test_safe_output_path_rejects_traversal():
    from api.paths import UnsafePath, safe_output_path

    assert safe_output_path("output/x.docx") == (config.OUTPUT_DIR / "x.docx").resolve()
    for bad in ("../x", "output/../../x", "C:/Windows/win.ini", "", "/etc/passwd"):
        with pytest.raises(UnsafePath):
            safe_output_path(bad)
