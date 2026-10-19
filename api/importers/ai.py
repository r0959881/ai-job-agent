"""Groq helpers for imports. Same rule as tailor.py: never invent facts."""
import copy
import json
import re

NO_FABRICATION = (
    "CRITICAL RULE: only use facts that appear in the input. Do not invent, embellish or assume any "
    "experience, skill, company, date, number or degree. If something is missing, leave it empty."
)


def call_json(prompt, client=None):
    """Ask Groq for a JSON object and parse it (tolerates text around the JSON)."""
    from tailor import MODEL, get_client

    client = client or get_client()
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    text = response.choices[0].message.content or ""
    try:
        return json.loads(text)
    except ValueError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise ValueError("Groq did not return JSON.") from None
        return json.loads(match.group(0))


def enrich_linkedin_draft(draft, extras, client=None):
    """Split descriptions into bullets, sort skills into categories, suggest project tech stacks.

    Returns (draft, extras, ai_fields {item_id: [field]}, warnings). Failures degrade to the plain import.
    """
    from api.services import resume_store

    current, _etag, _warnings = resume_store.load()
    categories = list(current.core_skills) or ["languages_and_tools", "platforms_and_cloud", "bi_and_reporting"]
    payload = {
        "experience": [{"index": i, "role": e["role"], "company": e["company"], "text": " ".join(e["bullets"])}
                       for i, e in enumerate(draft.get("experience", []))],
        "projects": [{"index": i, "title": p["title"], "text": " ".join(p["highlights"])}
                     for i, p in enumerate(draft.get("projects", []))],
        "skills": extras.get("skills_pool", []),
        "categories": categories,
    }
    prompt = f"""You clean up a LinkedIn profile export for a CV. {NO_FABRICATION}

Input JSON:
{json.dumps(payload, ensure_ascii=False)}

Tasks:
1. For each experience, split "text" into 2-6 concise CV bullet points, reusing the original wording.
2. For each project, split "text" into bullet points and list the technologies it explicitly names as "tech_stack".
3. Assign each skill to exactly one of the given categories (use the category names exactly).

Return JSON: {{"experience": [{{"index": 0, "bullets": ["..."]}}],
"projects": [{{"index": 0, "highlights": ["..."], "tech_stack": "A, B"}}],
"skill_categories": {{"Skill name": "category_name"}}}}"""
    try:
        result = call_json(prompt, client)
    except Exception as exc:
        from tailor import describe_error

        return draft, extras, {}, [f"“Enhance with AI” was skipped: {describe_error(exc)}. The plain import is shown."]

    draft, extras = copy.deepcopy(draft), copy.deepcopy(extras)
    ai_fields: dict[str, list[str]] = {}
    for entry in result.get("experience") or []:
        index = entry.get("index")
        if isinstance(index, int) and 0 <= index < len(draft["experience"]) and entry.get("bullets"):
            draft["experience"][index]["bullets"] = [str(b).strip() for b in entry["bullets"] if str(b).strip()]
            ai_fields.setdefault(f"experience:{index}", []).append("bullets")
    for entry in result.get("projects") or []:
        index = entry.get("index")
        if isinstance(index, int) and 0 <= index < len(draft["projects"]):
            if entry.get("highlights"):
                draft["projects"][index]["highlights"] = [str(h).strip() for h in entry["highlights"] if str(h).strip()]
                ai_fields.setdefault(f"projects:{index}", []).append("highlights")
            if entry.get("tech_stack"):
                draft["projects"][index]["tech_stack"] = str(entry["tech_stack"]).strip()
                ai_fields.setdefault(f"projects:{index}", []).append("tech_stack")
    assignments = result.get("skill_categories") or {}
    extras["skill_categories"] = {
        skill: category for skill, category in assignments.items()
        if skill in extras.get("skills_pool", []) and category in categories
    }
    return draft, extras, ai_fields, []


RESUME_SCHEMA = """{
  "personal_info": {"full_name": "", "headline": "", "email": "", "phone": "", "location": ""},
  "core_skills": {"category_name_in_snake_case": ["Skill"]},
  "experience": [{"company": "", "role": "", "location": "", "dates": "Mon YYYY - Mon YYYY or Present",
                  "type": "Professional Experience or Internship", "bullets": [""]}],
  "projects": [{"title": "", "tech_stack": "A, B", "highlights": [""]}],
  "certifications": [{"name": "", "issuer": "", "year": "YYYY"}],
  "education": {"degree": "", "institution": "", "location": "", "dates": "", "coursework": [""]},
  "languages": ["Language: level"],
  "low_confidence": ["paths like experience.0.dates or personal_info.phone that you are unsure about"]
}"""


def extract_resume(text, client=None):
    """Turn resume text into the resume_data.yaml structure. Returns (draft, low_confidence paths)."""
    prompt = f"""Extract this resume into JSON with exactly this structure:
{RESUME_SCHEMA}

{NO_FABRICATION}
Copy bullet points as written. Use "Mon YYYY" dates where the resume has them. If the resume has more than
one education entry, use the most recent. List in "low_confidence" every field you had to guess or that was
hard to read (for example dates split across lines).

Resume text:
\"\"\"
{text[:30000]}
\"\"\""""
    result = call_json(prompt, client)
    low = []
    for path in result.pop("low_confidence", []) or []:
        parts = str(path).split(".")
        if len(parts) >= 2 and parts[1].isdigit():
            low.append(f"{parts[0]}:{parts[1]}" + (f".{'.'.join(parts[2:])}" if parts[2:] else ""))
        elif parts[0] == "personal_info" and len(parts) == 2:
            low.append(f"personal_info:{parts[1]}")
        elif parts[0] == "education":
            low.append("education:main")
    return result, low
