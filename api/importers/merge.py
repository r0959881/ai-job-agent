"""Merge an imported draft into the current resume without overwriting anything silently.

`diff_items(current, draft)` labels every imported item as new, matching or
conflict. `apply_decisions(...)` applies the user's choices:

    new       -> "add" (default) | "skip"
    conflict  -> "keep_mine" (default) | "use_import" | "keep_both"
    matching  -> nothing to do
"""
import copy
import re

LIST_SECTIONS = {
    "experience": lambda item: (_key(item.get("company")), _key(item.get("role"))),
    "projects": lambda item: _key(item.get("title")),
    "certifications": lambda item: _key(item.get("name")),
    "languages": lambda item: _key(str(item).split(":")[0]),
}
LABELS = {
    "experience": lambda item: " · ".join(p for p in (item.get("role"), item.get("company")) if p),
    "projects": lambda item: item.get("title", ""),
    "certifications": lambda item: item.get("name", ""),
    "languages": lambda item: str(item),
}
PERSONAL_FIELDS = ["full_name", "headline", "email", "phone", "location"]
DEFAULT_ACTION = {"new": "add", "conflict": "keep_mine", "matching": "keep_mine"}


def _key(value):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", str(value or "").lower())).strip()


def _empty(value):
    return value in (None, "", [], {})


def _changed_fields(current, imported):
    if not isinstance(imported, dict):
        return [] if _key(current) == _key(imported) else ["value"]
    changed = []
    for field, value in imported.items():
        if _empty(value):
            continue
        mine = current.get(field) if isinstance(current, dict) else None
        if isinstance(value, list):
            if [_key(v) for v in value] != [_key(v) for v in (mine or [])]:
                changed.append(field)
        elif _key(value) != _key(mine):
            changed.append(field)
    return changed


def diff_items(current, draft, ai_fields=None, low_confidence=()):
    """Every importable item with a stable id, its status and what changed."""
    ai_fields = ai_fields or {}
    items = []
    personal_now = current.get("personal_info") or {}
    for field in PERSONAL_FIELDS:
        value = (draft.get("personal_info") or {}).get(field)
        if _empty(value):
            continue
        mine = personal_now.get(field)
        status = "new" if _empty(mine) else "matching" if _key(mine) == _key(value) else "conflict"
        items.append(_item(f"personal_info:{field}", "personal_info", field.replace("_", " ").capitalize(), status,
                           mine, value, ["value"] if status == "conflict" else [], ai_fields, low_confidence))

    for section, identity in LIST_SECTIONS.items():
        existing = {identity(item): (index, item) for index, item in enumerate(current.get(section) or [])}
        seen = set()
        for index, imported in enumerate(draft.get(section) or []):
            key = identity(imported)
            if key in seen:
                continue
            seen.add(key)
            item_id = f"{section}:{index}"
            if key in existing:
                _pos, mine = existing[key]
                changed = _changed_fields(mine, imported)
                status = "conflict" if changed else "matching"
                items.append(_item(item_id, section, LABELS[section](imported), status, mine, imported, changed,
                                   ai_fields, low_confidence))
            else:
                items.append(_item(item_id, section, LABELS[section](imported), "new", None, imported, [],
                                   ai_fields, low_confidence))

    education = draft.get("education") or {}
    if education.get("institution") or education.get("degree"):
        mine = current.get("education") or {}
        if not (mine.get("institution") or mine.get("degree")):
            status, changed = "new", []
        else:
            changed = _changed_fields(mine, education)
            status = "conflict" if changed else "matching"
        label = " · ".join(p for p in (education.get("degree"), education.get("institution")) if p)
        items.append(_item("education:main", "education", label, status, mine or None, education, changed,
                           ai_fields, low_confidence))
    return items


def _item(item_id, section, label, status, current, imported, changed, ai_fields, low_confidence):
    return {
        "id": item_id, "section": section, "label": label, "status": status,
        "current": copy.deepcopy(current), "imported": copy.deepcopy(imported), "changed_fields": changed,
        "ai_fields": list(ai_fields.get(item_id, [])),
        "low_confidence": any(path == item_id or path.startswith(f"{item_id}.") for path in low_confidence),
    }


def _merge_item(mine, imported):
    """Use the import's non-empty fields, keep mine for the rest (and any extra keys)."""
    if not isinstance(mine, dict):
        return imported
    merged = copy.deepcopy(mine)
    for field, value in imported.items():
        if not _empty(value):
            merged[field] = copy.deepcopy(value)
    return merged


def apply_decisions(current, draft, decisions, skills=None, education_choice=None):
    """Return a new resume dict with the accepted import decisions applied."""
    result = copy.deepcopy(current)
    if education_choice is not None:
        alternatives = draft.get("education_alternatives") or []
        if 0 <= education_choice < len(alternatives):
            draft = {**draft, "education": alternatives[education_choice]}
    for item in diff_items(current, draft):
        action = decisions.get(item["id"], DEFAULT_ACTION[item["status"]])
        section, imported = item["section"], item["imported"]
        if item["status"] == "matching" or action in {"skip", "keep_mine"}:
            continue
        if section == "personal_info":
            if action in {"add", "use_import"}:
                result.setdefault("personal_info", {})[item["id"].split(":", 1)[1]] = imported
        elif section == "education":
            if action in {"add", "use_import"}:
                result["education"] = _merge_item(result.get("education") or {}, imported)
        else:
            entries = result.setdefault(section, [])
            if item["status"] == "conflict" and action == "use_import":
                identity = LIST_SECTIONS[section]
                for index, entry in enumerate(entries):
                    if identity(entry) == identity(imported):
                        entries[index] = _merge_item(entry, imported) if isinstance(entry, dict) else imported
                        break
            elif action in {"add", "keep_both"}:
                entries.append(copy.deepcopy(imported))
    for category, names in (skills or {}).items():
        category = category.strip()
        if not category or not names:
            continue
        bucket = result.setdefault("core_skills", {}).setdefault(category, [])
        known = {_key(name) for values in result["core_skills"].values() for name in values}
        for name in names:
            if _key(name) not in known:
                bucket.append(name)
                known.add(_key(name))
    return result


def new_skills(current, pool):
    known = {_key(skill) for skills in (current.get("core_skills") or {}).values() for skill in skills}
    return [skill for skill in pool if _key(skill) not in known]


def build_import_result(source, draft, warnings, extras=None, ai_fields=None, ai_used=False, low_confidence=(),
                        preview_html=None):
    """Shape the API response for the review screen (nothing is saved)."""
    from api.models.resume import Resume
    from api.services import resume_store

    current_model, _etag, _warnings = resume_store.load()
    current = resume_store.to_plain(current_model)
    extras = extras or {}
    full_draft = Resume.model_validate(draft).model_dump(mode="json")
    # Skills never overwrite categories directly: they go to a pool the user sorts into categories.
    suggestions = dict(extras.get("skill_categories") or {})
    pool = list(extras.get("skills_pool") or [])
    for category, names in (draft.get("core_skills") or {}).items():
        for name in names:
            pool.append(name)
            suggestions.setdefault(name, category)
    pool = new_skills(current, list(dict.fromkeys(pool)))
    full_draft["core_skills"] = {}
    return {
        "source": source,
        "draft": full_draft,
        "items": diff_items(current, draft, ai_fields, low_confidence),
        "warnings": warnings,
        "skills_pool": pool,
        "skill_suggestions": {name: suggestions[name] for name in pool if name in suggestions},
        "education_alternatives": extras.get("education_alternatives", []),
        "low_confidence": list(low_confidence),
        "ai_used": ai_used,
        "preview_html": preview_html,
        "current_empty": not current["personal_info"].get("full_name") and not current["experience"],
    }
