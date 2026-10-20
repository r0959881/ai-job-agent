"""LinkedIn export importer, merge decisions and resume-file import."""
import copy
import io
import json
import zipfile

import pytest
import yaml
from helpers import FakeGroq, resume_text, set_resume_text, set_secret

from api.importers.linkedin import LinkedInImportError, format_date, parse_linkedin_zip, split_bullets
from api.importers.merge import apply_decisions, diff_items

PROFILE = "First Name,Last Name,Headline,Summary,Geo Location\nAda,Lovelace,Data Analyst,Loves data,\"Gent, Belgium\"\n"
POSITIONS = (
    "Company Name,Title,Description,Location,Started On,Finished On\n"
    "Acme NV,Junior Data Analyst,\"Built dashboards\nWrote SQL\",Gent,Jun 2025,\n"
    "Beta BV,Intern,• Cleaned data • Automated reports,Antwerp,2024-02,2024-06\n"
)


def make_zip(files, extra=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
        for name, content in (extra or {}).items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_parses_the_core_files_with_bom_preamble_and_renamed_columns():
    skills = "﻿Notes:\n\"This file lists your skills.\"\n\nName\nSQL\nPower BI\nsql\n"
    education = (
        "School Name,Start Date,End Date,Notes,Degree Name,Activities\n"
        "Old School,2015,2018,Math,High school,\n"
        "Thomas More,2023,2026,Data Science,Bachelor,\n"
    )
    certs = "Name,Url,Authority,Started On,Finished On,License Number\nPL-300,,Microsoft,Mar 2026,,\n"
    languages = "Name,Proficiency\nDutch,Limited working proficiency\nEnglish,\n"
    emails = "Email Address,Confirmed,Primary,Updated On\nold@example.com,Yes,No,\nada@example.com,Yes,Yes,\n"
    phones = "Extension,Number,Type\n,+32 400 11 22 33,Mobile\n"
    # Renamed column: "Organization" instead of "Company Name", "Position" instead of "Title".
    positions = POSITIONS.replace("Company Name,Title", "Organization,Position")
    data = make_zip({
        "Basic_LinkedInDataExport/Profile.csv": PROFILE.encode("utf-8-sig"),
        "Basic_LinkedInDataExport/Positions.csv": positions,
        "Skills.csv": skills.encode("utf-8"),
        "Education.csv": education,
        "Certifications.csv": certs,
        "Languages.csv": languages.encode("latin-1"),
        "Email Addresses.csv": emails,
        "PhoneNumbers.csv": phones,
        "messages.csv": "From,To,Content\nsomeone,me,private message\n",
        "Connections.csv": "First Name,Last Name\nPrivate,Person\n",
    })
    draft, warnings, extras = parse_linkedin_zip(data)
    assert draft["personal_info"] == {"full_name": "Ada Lovelace", "headline": "Data Analyst", "location": "Gent, Belgium",
                                      "email": "ada@example.com", "phone": "+32 400 11 22 33"}
    assert draft["experience"][0] == {"company": "Acme NV", "role": "Junior Data Analyst", "location": "Gent",
                                      "dates": "Jun 2025 - Present", "type": "",
                                      "bullets": ["Built dashboards", "Wrote SQL"]}
    assert draft["experience"][1]["dates"] == "Feb 2024 - Jun 2024"
    assert draft["experience"][1]["bullets"] == ["Cleaned data", "Automated reports"]
    assert draft["education"]["institution"] == "Thomas More"
    assert [e["institution"] for e in extras["education_alternatives"]] == ["Thomas More", "Old School"]
    assert draft["certifications"] == [{"name": "PL-300", "issuer": "Microsoft", "year": "2026"}]
    assert draft["languages"] == ["Dutch: Limited working proficiency", "English"]
    assert extras["skills_pool"] == ["SQL", "Power BI"]
    assert any("summary" in w for w in warnings)
    assert "private message" not in json.dumps([draft, extras])


def test_missing_files_produce_warnings_not_errors():
    draft, warnings, _extras = parse_linkedin_zip(make_zip({"Profile.csv": PROFILE}))
    assert draft["experience"] == []
    assert any("Positions.csv" in w for w in warnings) and any("Skills.csv" in w for w in warnings)


def test_rejects_non_zip_empty_and_unrelated_archives():
    with pytest.raises(LinkedInImportError, match="not a .zip"):
        parse_linkedin_zip(b"hello")
    with pytest.raises(LinkedInImportError, match="No LinkedIn profile files"):
        parse_linkedin_zip(make_zip({"notes.txt": "x"}))


def test_zip_slip_entries_are_skipped():
    data = make_zip({"../../Profile.csv": PROFILE, "Positions.csv": POSITIONS})
    draft, warnings, _ = parse_linkedin_zip(data)
    assert draft["personal_info"] == {}
    assert any("outside the archive" in w for w in warnings)
    assert len(draft["experience"]) == 2


def test_oversized_and_bomb_like_files_are_skipped(monkeypatch):
    import api.importers.linkedin as linkedin

    bomb = "Name\n" + "A" * (3 * 1024 * 1024)  # compresses far beyond the ratio limit
    draft, warnings, extras = parse_linkedin_zip(make_zip({"Skills.csv": bomb, "Positions.csv": POSITIONS}))
    assert extras["skills_pool"] == [] and any("zip bomb" in w for w in warnings)

    monkeypatch.setattr(linkedin, "MAX_FILE_UNCOMPRESSED", 100)
    _draft, warnings, _ = parse_linkedin_zip(make_zip({"Positions.csv": POSITIONS, "Profile.csv": PROFILE[:90]}))
    assert any("Positions.csv" in w and "larger than" in w for w in warnings)

    monkeypatch.setattr(linkedin, "MAX_ZIP_BYTES", 10)
    with pytest.raises(LinkedInImportError, match="larger than 50 MB"):
        parse_linkedin_zip(make_zip({"Profile.csv": PROFILE}))


def test_row_cap(monkeypatch):
    import api.importers.linkedin as linkedin

    monkeypatch.setattr(linkedin, "MAX_ROWS", 2)
    skills = "Name\n" + "\n".join(f"Skill {i}" for i in range(10))
    _draft, warnings, extras = parse_linkedin_zip(make_zip({"Skills.csv": skills}))
    assert len(extras["skills_pool"]) == 2 and any("first 2 rows" in w for w in warnings)


@pytest.mark.parametrize("raw,expected", [
    ("Jun 2026", "Jun 2026"), ("June 2026", "Jun 2026"), ("2026-06", "Jun 2026"), ("06/2026", "Jun 2026"),
    ("2026", "2026"), ("Jun 12, 2026", "Jun 2026"), ("", ""),
])
def test_date_formats(raw, expected):
    assert format_date(raw) == expected


def test_unparseable_dates_warn():
    warnings = []
    assert format_date("summer 2025", warnings, "Position X") == "summer 2025"
    assert "summer 2025" in warnings[0]


def test_split_bullets():
    assert split_bullets("One\n- Two\n• Three") == ["One", "Two", "Three"]
    assert split_bullets("") == []


# ---------------------------------------------------------------- merge

CURRENT = {
    "personal_info": {"full_name": "Ada Lovelace", "headline": "Analyst", "email": "", "phone": "1", "location": ""},
    "experience": [{"company": "Acme NV", "role": "Junior Data Analyst", "location": "Gent", "dates": "2025",
                    "type": "Job", "bullets": ["Old bullet"], "team": "BI"}],
    "projects": [{"title": "Dashboards", "tech_stack": "Power BI", "highlights": ["x"]}],
    "certifications": [], "languages": ["English: C1"], "core_skills": {"bi": ["Power BI"]},
    "education": {"degree": "BSc", "institution": "Uni", "location": "", "dates": "", "coursework": []},
}
DRAFT = {
    "personal_info": {"full_name": "Ada Lovelace", "headline": "Data Analyst", "email": "ada@example.com"},
    "experience": [
        {"company": "ACME nv", "role": "Junior data analyst", "location": "Gent", "dates": "Jun 2025 - Present",
         "type": "", "bullets": ["New bullet"]},
        {"company": "Beta", "role": "Intern", "location": "", "dates": "2024", "type": "", "bullets": []},
    ],
    "projects": [{"title": "Dashboards", "tech_stack": "Power BI", "highlights": ["x"]}],
    "certifications": [{"name": "PL-300", "issuer": "Microsoft", "year": "2026"}],
    "languages": ["English: B2", "Dutch: A2"],
    "education": {"degree": "BSc", "institution": "Uni"},
}


def statuses(items):
    return {item["id"]: (item["status"], item["changed_fields"]) for item in items}


def test_diff_labels_new_matching_and_conflicts():
    result = statuses(diff_items(CURRENT, DRAFT))
    assert result["personal_info:full_name"] == ("matching", [])
    assert result["personal_info:headline"] == ("conflict", ["value"])
    assert result["personal_info:email"] == ("new", [])
    assert result["experience:0"] == ("conflict", ["dates", "bullets"])
    assert result["experience:1"] == ("new", [])
    assert result["projects:0"] == ("matching", [])
    assert result["certifications:0"] == ("new", [])
    assert result["languages:0"] == ("conflict", ["value"]) and result["languages:1"] == ("new", [])
    assert result["education:main"] == ("matching", [])


def test_default_decisions_add_new_and_keep_mine():
    merged = apply_decisions(CURRENT, DRAFT, {})
    assert merged["personal_info"]["headline"] == "Analyst"
    assert merged["personal_info"]["email"] == "ada@example.com"
    assert [e["company"] for e in merged["experience"]] == ["Acme NV", "Beta"]
    assert merged["experience"][0]["bullets"] == ["Old bullet"]
    assert merged["languages"] == ["English: C1", "Dutch: A2"]
    assert merged["certifications"][0]["name"] == "PL-300"
    assert CURRENT["experience"][0]["bullets"] == ["Old bullet"]  # input untouched


def test_use_import_keep_both_and_skip():
    decisions = {"experience:0": "use_import", "languages:0": "keep_both", "experience:1": "skip",
                 "personal_info:headline": "use_import", "certifications:0": "skip"}
    merged = apply_decisions(CURRENT, DRAFT, decisions, skills={"bi": ["Tableau", "power bi"], "cloud": ["Azure"]})
    first = merged["experience"][0]
    assert first["bullets"] == ["New bullet"] and first["dates"] == "Jun 2025 - Present"
    assert first["type"] == "Job" and first["team"] == "BI"  # kept where the import had nothing
    assert len(merged["experience"]) == 1 and merged["certifications"] == []
    assert merged["languages"] == ["English: C1", "English: B2", "Dutch: A2"]
    assert merged["personal_info"]["headline"] == "Data Analyst"
    assert merged["core_skills"] == {"bi": ["Power BI", "Tableau"], "cloud": ["Azure"]}


def test_education_choice_picks_an_alternative():
    draft = copy.deepcopy(DRAFT)
    draft["education_alternatives"] = [draft["education"], {"degree": "MSc", "institution": "Other"}]
    merged = apply_decisions(CURRENT, draft, {"education:main": "use_import"}, education_choice=1)
    assert merged["education"]["degree"] == "MSc" and merged["education"]["institution"] == "Other"


# ---------------------------------------------------------------- API


def test_linkedin_import_is_not_saved_until_committed(client):
    before = resume_text()
    upload = make_zip({"Profile.csv": PROFILE, "Positions.csv": POSITIONS, "Skills.csv": "Name\nSQL\nKubernetes\n"})
    response = client.post("/api/resume/import/linkedin", files={"file": ("export.zip", upload, "application/zip")})
    assert response.status_code == 200, response.text
    result = response.json()
    assert resume_text() == before
    assert {i["status"] for i in result["items"]} >= {"new", "conflict"}
    assert "Kubernetes" in result["skills_pool"] and "SQL" not in [s for s in result["skills_pool"] if s == "SQL (Advanced)"]

    commit = client.post("/api/resume/import/commit", json={
        "draft": result["draft"],
        "decisions": {"personal_info:headline": "keep_mine"},
        "skills": {"devops_and_orchestration": ["Kubernetes"]},
    })
    assert commit.status_code == 200, commit.text
    saved = yaml.safe_load(resume_text())
    companies = [e["company"] for e in saved["experience"]]
    assert "Acme NV" in companies and "Estée Lauder Companies" in companies
    assert "Kubernetes" in saved["core_skills"]["devops_and_orchestration"]
    assert saved["personal_info"]["full_name"] == "Ammar Haider"  # conflict kept mine by default
    assert client.get("/api/resume/backups").json()[0]["label"] == "Before an import"


def test_linkedin_upload_errors_are_readable(client):
    response = client.post("/api/resume/import/linkedin", files={"file": ("x.zip", b"not a zip", "application/zip")})
    assert response.status_code == 400 and "not a .zip" in response.json()["detail"]
    response = client.post("/api/resume/import/linkedin", files={"file": ("x.zip", b"", "application/zip")})
    assert response.status_code == 400


def make_docx(lines):
    from docx import Document

    document = Document()
    for line in lines:
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


class ResumeJsonGroq(FakeGroq):
    def __init__(self, payload):
        super().__init__()
        self.completions.create = lambda **_k: type("R", (), {"choices": [type("C", (), {
            "message": type("M", (), {"content": json.dumps(payload)})})]})


def test_resume_file_import_into_an_empty_profile(client, monkeypatch):
    import tailor

    set_resume_text("")
    payload = {"personal_info": {"full_name": "Grace Hopper", "email": "grace@example.com"},
               "core_skills": {"languages_and_tools": ["COBOL"]},
               "experience": [{"company": "Navy", "role": "Engineer", "dates": "1943 - 1986", "bullets": ["Compilers"]},
                              {"company": "", "role": "Ghost"}],
               "education": {"degree": "PhD", "institution": "Yale"}, "languages": ["English: native"],
               "low_confidence": ["experience.0.dates", "personal_info.phone"]}
    set_secret("GROQ_API_KEY", "gsk_test")
    monkeypatch.setattr(tailor, "get_client", lambda: ResumeJsonGroq(payload))
    upload = make_docx(["Grace Hopper", "grace@example.com"] + ["Lots of experience text here."] * 20)
    response = client.post("/api/resume/import", files={"file": ("cv.docx", upload)})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["current_empty"] and "Grace Hopper" in result["preview_html"]
    assert len(result["draft"]["experience"]) == 1  # the incomplete entry was dropped
    exp = next(i for i in result["items"] if i["id"] == "experience:0")
    assert exp["low_confidence"] and exp["status"] == "new"
    assert result["skills_pool"] == ["COBOL"] and result["skill_suggestions"] == {"COBOL": "languages_and_tools"}

    commit = client.post("/api/resume/import/commit", json={"draft": result["draft"], "decisions": {},
                                                             "skills": {"languages_and_tools": ["COBOL"]}})
    assert commit.status_code == 200, commit.text
    saved = yaml.safe_load(resume_text())
    assert saved["personal_info"]["full_name"] == "Grace Hopper"
    assert saved["experience"][0]["company"] == "Navy" and saved["core_skills"] == {"languages_and_tools": ["COBOL"]}


def test_resume_file_import_needs_groq_and_real_text(client):
    upload = make_docx(["Short"])
    assert "Almost no text" in client.post("/api/resume/import", files={"file": ("cv.docx", upload)}).json()["detail"]
    upload = make_docx(["Plenty of words in this resume line."] * 20)
    detail = client.post("/api/resume/import", files={"file": ("cv.docx", upload)}).json()["detail"]
    assert "Groq API key" in detail
    assert client.post("/api/resume/import", files={"file": ("cv.txt", b"plain")}).status_code == 400
