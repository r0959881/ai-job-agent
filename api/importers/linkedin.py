"""Read a LinkedIn "Get a copy of your data" export into the resume_data.yaml shape.

`parse_linkedin_zip(data)` is pure: zip bytes in, (draft, warnings, extras) out.
The archive is read in memory, only known profile CSVs are opened (never
messages or connections), and nothing is written to disk.
"""
import csv
import io
import posixpath
import re
import zipfile
from datetime import datetime

MAX_ZIP_BYTES = 50 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED = 60 * 1024 * 1024
MAX_FILE_UNCOMPRESSED = 15 * 1024 * 1024
MAX_ENTRIES = 5000
MAX_ROWS = 5000
MAX_RATIO = 200  # compressed -> uncompressed; higher looks like a zip bomb

KNOWN_FILES = {
    "profile.csv": "profile",
    "positions.csv": "positions",
    "education.csv": "education",
    "skills.csv": "skills",
    "certifications.csv": "certifications",
    "languages.csv": "languages",
    "projects.csv": "projects",
    "email addresses.csv": "emails",
    "phonenumbers.csv": "phones",
}

# Normalised header -> field. LinkedIn renames columns now and then, so several spellings map to one field.
ALIASES = {
    "profile": {
        "first_name": ["firstname", "givenname"],
        "last_name": ["lastname", "familyname", "surname"],
        "headline": ["headline", "title"],
        "summary": ["summary", "about"],
        "location": ["geolocation", "location", "geo", "address"],
    },
    "positions": {
        "company": ["companyname", "company", "organization", "organisation", "employer"],
        "role": ["title", "position", "jobtitle", "role"],
        "description": ["description", "summary"],
        "location": ["location", "geolocation"],
        "start": ["startedon", "startdate", "start", "from"],
        "end": ["finishedon", "enddate", "end", "to"],
    },
    "education": {
        "institution": ["schoolname", "school", "institution", "university"],
        "degree": ["degreename", "degree", "qualification"],
        "field": ["fieldofstudy", "notes", "field", "major"],
        "start": ["startdate", "startedon", "start"],
        "end": ["enddate", "finishedon", "end"],
        "activities": ["activities", "activitiesandsocieties"],
    },
    "skills": {"name": ["name", "skill", "skillname"]},
    "certifications": {
        "name": ["name", "certificationname", "title"],
        "issuer": ["authority", "issuer", "issuingorganization", "organization"],
        "start": ["startedon", "issuedon", "startdate", "issuedate", "date"],
        "url": ["url"],
    },
    "languages": {"name": ["name", "language"], "proficiency": ["proficiency", "level"]},
    "projects": {
        "title": ["title", "name", "projectname"],
        "description": ["description", "summary"],
        "url": ["url", "link"],
        "start": ["startedon", "startdate", "start"],
        "end": ["finishedon", "enddate", "end"],
    },
    "emails": {"email": ["emailaddress", "email"], "primary": ["primary", "isprimary"], "confirmed": ["confirmed"]},
    "phones": {"number": ["number", "phonenumber", "phone"], "type": ["type"]},
}

DISPLAY_NAMES = {
    name.lower(): name for name in (
        "Profile.csv", "Positions.csv", "Education.csv", "Skills.csv", "Certifications.csv", "Languages.csv",
        "Projects.csv", "Email Addresses.csv", "PhoneNumbers.csv",
    )
}

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


class LinkedInImportError(Exception):
    """The upload cannot be read as a LinkedIn export at all."""


def _norm(header):
    return re.sub(r"[^a-z0-9]", "", (header or "").lower())


def decode(raw):
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _header_index(lines, kind):
    """LinkedIn sometimes puts note lines above the header; find the real header row."""
    wanted = {alias for aliases in ALIASES[kind].values() for alias in aliases}
    for index, line in enumerate(lines[:30]):
        try:
            cells = next(csv.reader([line]))
        except (csv.Error, StopIteration):
            continue
        hits = sum(_norm(cell) in wanted for cell in cells)
        if hits >= min(2, len(ALIASES[kind])) or (len(ALIASES[kind]) <= 2 and hits >= 1 and len(cells) <= 4):
            return index
    return None


def read_rows(text, kind, file_name, warnings):
    lines = text.splitlines()
    start = _header_index(lines, kind)
    if start is None:
        warnings.append(f"{file_name}: could not find the header row, so it was skipped.")
        return []
    reader = csv.reader(io.StringIO("\n".join(lines[start:])))
    try:
        header = next(reader)
    except StopIteration:
        return []
    columns = {}
    normalised = [_norm(h) for h in header]
    for field, aliases in ALIASES[kind].items():
        for alias in aliases:
            if alias in normalised:
                columns[field] = normalised.index(alias)
                break
    rows = []
    for count, cells in enumerate(reader):
        if count >= MAX_ROWS:
            warnings.append(f"{file_name}: only the first {MAX_ROWS} rows were read.")
            break
        if not any(cell.strip() for cell in cells):
            continue
        rows.append({field: (cells[i].strip() if i < len(cells) else "") for field, i in columns.items()})
    return rows


def format_date(value, warnings=None, context=""):
    """LinkedIn dates ('Jun 2026', '2026-06', '06/2026', '2026', 'Jun 12, 2026') -> 'Jun 2026'."""
    value = (value or "").strip()
    if not value:
        return ""
    for fmt in ("%b %Y", "%B %Y", "%Y-%m", "%m/%Y", "%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%m/%d/%Y"):
        try:
            parsed = datetime.strptime(value, fmt)
            return f"{MONTHS[parsed.month - 1]} {parsed.year}"
        except ValueError:
            continue
    if re.fullmatch(r"\d{4}", value):
        return value
    if warnings is not None:
        warnings.append(f"{context}: the date “{value}” was not recognised and was kept as written.")
    return value


def _sort_key(text):
    """Sortable (year, month) from a formatted date; empty sorts as 'now' for end dates."""
    match = re.match(r"(?:(\w{3}) )?(\d{4})", text or "")
    if not match:
        return (0, 0)
    month = MONTHS.index(match.group(1)) + 1 if match.group(1) in MONTHS else 0
    return (int(match.group(2)), month)


def split_bullets(text):
    """Split a description into bullet lines on line breaks and bullet glyphs."""
    if not text:
        return []
    parts = re.split(r"\r?\n|(?:^|\s)[•▪●◦·]\s+", text)
    bullets = []
    for part in parts:
        cleaned = re.sub(r"^[\s•▪●◦·\-*–]+", "", part or "").strip()
        if len(cleaned) > 2:
            bullets.append(cleaned)
    return bullets


def _safe_member(name):
    normalised = posixpath.normpath(name.replace("\\", "/"))
    return not (normalised.startswith("../") or normalised == ".." or normalised.startswith("/")
                or re.match(r"^[A-Za-z]:", normalised))


def open_known_files(data, warnings):
    """Return {kind: text} for the known CSVs in the archive, with size and path guards."""
    if len(data) > MAX_ZIP_BYTES:
        raise LinkedInImportError("The file is larger than 50 MB. LinkedIn profile exports are much smaller.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise LinkedInImportError("This is not a .zip file. Upload the archive LinkedIn emailed you.") from exc
    infos = archive.infolist()
    if len(infos) > MAX_ENTRIES:
        raise LinkedInImportError(f"The archive has more than {MAX_ENTRIES} files, which is not a LinkedIn export.")
    found, total = {}, 0
    for info in infos:
        if info.is_dir():
            continue
        lower = posixpath.basename(info.filename.replace("\\", "/")).lower()
        kind = KNOWN_FILES.get(lower)
        if not kind:
            continue  # Messages, connections, invitations... are never opened.
        base = DISPLAY_NAMES[lower]
        if not _safe_member(info.filename):
            warnings.append(f"Skipped “{info.filename}”: its path points outside the archive.")
            continue
        if info.file_size > MAX_FILE_UNCOMPRESSED:
            warnings.append(f"Skipped {base}: it is larger than {MAX_FILE_UNCOMPRESSED // (1024 * 1024)} MB.")
            continue
        if info.compress_size and info.file_size / info.compress_size > MAX_RATIO and info.file_size > 1024 * 1024:
            warnings.append(f"Skipped {base}: it is compressed suspiciously well (possible zip bomb).")
            continue
        total += info.file_size
        if total > MAX_TOTAL_UNCOMPRESSED:
            raise LinkedInImportError("The profile files are too large to import.")
        if kind in found:
            continue
        with archive.open(info) as handle:
            raw = handle.read(MAX_FILE_UNCOMPRESSED + 1)
        if len(raw) > MAX_FILE_UNCOMPRESSED:
            warnings.append(f"Skipped {base}: it is larger than it claimed to be.")
            continue
        found[kind] = (base, decode(raw))
    return found


def parse_linkedin_zip(data):
    """Pure: zip bytes -> (draft resume dict, warnings, extras {skills_pool, education_alternatives})."""
    warnings = []
    files = open_known_files(data, warnings)
    if not files:
        raise LinkedInImportError(
            "No LinkedIn profile files were found in this zip. Request “Profile”, “Positions” and “Skills” "
            "in LinkedIn's data export and upload that archive."
        )
    for name, kind in KNOWN_FILES.items():
        if kind not in files and kind in {"profile", "positions", "education", "skills"}:
            warnings.append(f"{DISPLAY_NAMES[name]} was missing or unreadable, so that section was not imported.")
    rows = {kind: read_rows(text, kind, base, warnings) for kind, (base, text) in files.items()}

    personal = {}
    if rows.get("profile"):
        profile = rows["profile"][0]
        name = " ".join(p for p in (profile.get("first_name"), profile.get("last_name")) if p).strip()
        personal.update({"full_name": name, "headline": profile.get("headline", ""),
                         "location": profile.get("location", "")})
        if profile.get("summary"):
            warnings.append("Your LinkedIn summary was not imported: each CV gets its own tailored summary.")
    emails = rows.get("emails") or []
    primary = next((e for e in emails if (e.get("primary") or "").lower() in {"yes", "true"}), emails[0] if emails else None)
    if primary and primary.get("email"):
        personal["email"] = primary["email"]
    phones = rows.get("phones") or []
    if phones and phones[0].get("number"):
        personal["phone"] = phones[0]["number"]

    experience = []
    for row in rows.get("positions") or []:
        if not row.get("company") or not row.get("role"):
            if row.get("company") or row.get("role"):
                warnings.append(f"A position without a {'title' if row.get('company') else 'company'} was skipped "
                                f"({row.get('company') or row.get('role')}).")
            continue
        context = f"Position “{row.get('role')}” at {row.get('company')}"
        start = format_date(row.get("start"), warnings, context)
        end = format_date(row.get("end"), warnings, context) or "Present"
        experience.append({
            "company": row.get("company", ""), "role": row.get("role", ""), "location": row.get("location", ""),
            "dates": f"{start} - {end}" if start else end, "type": "",
            "bullets": split_bullets(row.get("description", "")),
        })

    education_entries = []
    for row in rows.get("education") or []:
        if not row.get("institution"):
            continue
        start = format_date(row.get("start"), warnings, f"Education at {row['institution']}")
        end = format_date(row.get("end"), warnings, f"Education at {row['institution']}")
        degree = ", ".join(p for p in (row.get("degree"), row.get("field")) if p)
        education_entries.append({
            "degree": degree, "institution": row["institution"], "location": "",
            "dates": " - ".join(p for p in (start, end) if p), "coursework": [], "_end": end, "_start": start,
        })
    education_entries.sort(key=lambda e: (_sort_key(e["_end"]) if e["_end"] else (9999, 12), _sort_key(e["_start"])),
                           reverse=True)
    for entry in education_entries:
        entry.pop("_end")
        entry.pop("_start")

    certifications = []
    for row in rows.get("certifications") or []:
        if row.get("name"):
            date = format_date(row.get("start"), warnings, f"Certification “{row['name']}”")
            year = re.search(r"\d{4}", date or "")
            certifications.append({"name": row["name"], "issuer": row.get("issuer", ""),
                                   "year": year.group(0) if year else ""})

    languages = []
    for row in rows.get("languages") or []:
        if row.get("name"):
            languages.append(f"{row['name']}: {row['proficiency']}" if row.get("proficiency") else row["name"])

    projects = []
    for row in rows.get("projects") or []:
        if row.get("title"):
            projects.append({"title": row["title"], "tech_stack": "",
                             "highlights": split_bullets(row.get("description", ""))})

    skills_pool = []
    for row in rows.get("skills") or []:
        name = row.get("name", "").strip()
        if name and name.lower() not in {s.lower() for s in skills_pool}:
            skills_pool.append(name)

    draft = {
        "personal_info": personal,
        "experience": experience,
        "projects": projects,
        "certifications": certifications,
        "education": education_entries[0] if education_entries else {},
        "languages": languages,
    }
    extras = {"skills_pool": skills_pool, "education_alternatives": education_entries}
    return draft, warnings, extras


def import_linkedin_export(data, use_ai=False):
    """Parse the zip, optionally enrich it with Groq, and diff it against the current resume."""
    from api.importers.merge import build_import_result

    draft, warnings, extras = parse_linkedin_zip(data)
    ai_fields = {}
    ai_used = False
    if use_ai:
        from api.importers.ai import enrich_linkedin_draft

        draft, extras, ai_fields, ai_warnings = enrich_linkedin_draft(draft, extras)
        warnings += ai_warnings
        ai_used = bool(ai_fields)
    return build_import_result("linkedin", draft, warnings, extras, ai_fields=ai_fields, ai_used=ai_used)
