"""Read, validate and save resume_data.yaml.

Saves are atomic, keep a timestamped backup (last 20) and go through
ruamel.yaml so existing key order, quoting and comments survive.
"""
import hashlib
import io
import re
from datetime import UTC, datetime

from pydantic import ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import MarkedYAMLError
from ruamel.yaml.scalarstring import DoubleQuotedScalarString, SingleQuotedScalarString

import agent_settings
from api.models.resume import Resume, cross_reference_warnings, is_empty
from config import BACKUPS_DIR, RESUME_PATH, atomic_write_text

RESUME_BACKUPS = BACKUPS_DIR / "resume"
KEEP_BACKUPS = 20
BACKUP_NAME = re.compile(r"^resume_(\d{8}T\d{6}\d{6})(?:_([a-z_]+))?$")


class ResumeConflict(Exception):
    """The file changed on disk after the client loaded it."""


class ResumeInvalid(Exception):
    def __init__(self, errors, message="The resume has problems that need fixing before it can be saved."):
        super().__init__(message)
        self.message = message
        self.errors = errors


def _yaml():
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096
    yaml.indent(mapping=2, sequence=4, offset=2)
    return yaml


def read_text():
    try:
        return RESUME_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def etag_for(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def friendly_message(error):
    kind = error.get("type", "")
    if kind in {"string_too_short", "missing"}:
        return "This field is required."
    message = error.get("msg", "Invalid value")
    return message.removeprefix("Value error, ")


def validation_errors(exc: ValidationError):
    return [{"loc": [str(p) for p in err["loc"]], "msg": friendly_message(err)} for err in exc.errors()]


def validate(data) -> Resume:
    try:
        return Resume.model_validate(data or {})
    except ValidationError as exc:
        raise ResumeInvalid(validation_errors(exc)) from exc


def to_plain(resume: Resume):
    return resume.model_dump(mode="json")


def load():
    """Return (Resume, etag, warnings). A missing or empty file is an empty resume."""
    text = read_text()
    raw = _yaml().load(text) if text.strip() else {}
    resume = validate(_plain(raw))
    return resume, etag_for(text), cross_reference_warnings(resume, agent_settings.get("target_roles"))


def _plain(node):
    if isinstance(node, dict):
        return {str(k): _plain(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_plain(v) for v in node]
    if isinstance(node, str):
        return str(node)
    return node


# ---------------------------------------------------------------- round-trip merge

def _styled(old, value):
    """Keep the old scalar's quoting style for the new value."""
    if isinstance(value, str):
        if isinstance(old, DoubleQuotedScalarString):
            return DoubleQuotedScalarString(value)
        if isinstance(old, SingleQuotedScalarString):
            return SingleQuotedScalarString(value)
    return value


def _sibling_style(container):
    values = container.values() if isinstance(container, dict) else container
    for value in values:
        if isinstance(value, str):
            return value
    return None


def _fresh(value, style_hint=None):
    if isinstance(value, dict):
        mapping = CommentedMap()
        for key, item in value.items():
            mapping[key] = _fresh(item, style_hint)
        return mapping
    if isinstance(value, list):
        sequence = CommentedSeq()
        for item in value:
            sequence.append(_fresh(item, style_hint))
        return sequence
    if isinstance(value, str) and isinstance(style_hint, DoubleQuotedScalarString | SingleQuotedScalarString):
        return _styled(style_hint, value)
    return value


def merge_into(target, value, style_hint=None):
    """Update a ruamel node in place so comments, order and quoting survive."""
    if isinstance(target, CommentedMap) and isinstance(value, dict):
        hint = _sibling_style(target) or style_hint
        for key in [k for k in target if k not in value]:
            del target[key]
        for key, item in value.items():
            if key in target:
                target[key] = merge_into(target[key], item, hint)
            else:
                target[key] = _fresh(item, hint)
        # Follow the client's order (e.g. reordered skill categories), keeping comments with their keys.
        for key in value:
            target.move_to_end(key)
        return target
    if isinstance(target, CommentedSeq) and isinstance(value, list):
        hint = _sibling_style(target) or style_hint
        for index, item in enumerate(value):
            if index < len(target):
                target[index] = merge_into(target[index], item, hint)
            else:
                target.append(_fresh(item, hint))
        del target[len(value):]
        return target
    if isinstance(value, dict | list):
        return _fresh(value, style_hint)
    return _styled(target if target is not None else style_hint, value)


def dump_resume(resume: Resume, base_text=None):
    """Serialise to YAML text, reusing base_text's layout when given."""
    yaml = _yaml()
    plain = to_plain(resume)
    root = yaml.load(base_text) if base_text and base_text.strip() else None
    if not isinstance(root, CommentedMap):
        root = _fresh(plain, DoubleQuotedScalarString(""))
    else:
        merge_into(root, plain, DoubleQuotedScalarString(""))
    buffer = io.StringIO()
    yaml.dump(root, buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------- backups

def _backup_id(label):
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    return f"resume_{stamp}_{label}" if label else f"resume_{stamp}"


def backup_current(label="save"):
    text = read_text()
    if not text.strip():
        return None
    RESUME_BACKUPS.mkdir(parents=True, exist_ok=True)
    backup_id = _backup_id(label)
    atomic_write_text(RESUME_BACKUPS / f"{backup_id}.yaml", text)
    prune_backups()
    return backup_id


def prune_backups(keep=KEEP_BACKUPS):
    files = sorted(RESUME_BACKUPS.glob("resume_*.yaml"), reverse=True)
    for old in files[keep:]:
        old.unlink(missing_ok=True)


LABELS = {
    "save": "Before saving in the editor",
    "raw": "Before saving the YAML editor",
    "import": "Before an import",
    "restore": "Before restoring a backup",
}


def list_backups():
    items: list[dict] = []
    if not RESUME_BACKUPS.exists():
        return items
    for file in sorted(RESUME_BACKUPS.glob("resume_*.yaml"), reverse=True):
        match = BACKUP_NAME.match(file.stem)
        if not match:
            continue
        created = datetime.strptime(match.group(1), "%Y%m%dT%H%M%S%f").replace(tzinfo=UTC)
        items.append({
            "id": file.stem,
            "created_at": created.isoformat(),
            "size": file.stat().st_size,
            "label": LABELS.get(match.group(2) or "", "Backup"),
        })
    return items


def backup_path(backup_id):
    if not BACKUP_NAME.match(backup_id or ""):
        raise FileNotFoundError(backup_id)
    path = RESUME_BACKUPS / f"{backup_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(backup_id)
    return path


def read_backup(backup_id):
    return backup_path(backup_id).read_text(encoding="utf-8")


# ---------------------------------------------------------------- saving

def _check_etag(expected):
    if expected and expected != etag_for(read_text()):
        raise ResumeConflict(
            "resume_data.yaml changed on disk after you opened it. Reload to see the latest version."
        )


def save(data, etag=None, label="save"):
    """Validate structured data, back up the current file, then write atomically."""
    resume = validate(data)
    _check_etag(etag)
    base = read_text()
    text = dump_resume(resume, base)
    if text.rstrip("\n") == base.rstrip("\n"):
        return resume, etag_for(base), None  # Nothing changed: leave the file and its mtime alone.
    backup_id = backup_current(label)
    atomic_write_text(RESUME_PATH, text)
    return resume, etag_for(text), backup_id


def parse_raw(text):
    """Parse YAML text and validate it. Errors carry 1-based line numbers."""
    yaml = _yaml()
    try:
        root = yaml.load(text) if text.strip() else CommentedMap()
    except MarkedYAMLError as exc:
        mark = exc.problem_mark or exc.context_mark
        raise ResumeInvalid([{
            "line": mark.line + 1 if mark else None,
            "column": mark.column + 1 if mark else None,
            "message": f"YAML syntax error: {exc.problem or exc.context}",
        }], "The YAML could not be read.") from exc
    if root is None:
        root = CommentedMap()
    if not isinstance(root, dict):
        raise ResumeInvalid([{"line": 1, "column": 1, "message": "The top level must be a mapping of sections."}])
    try:
        return Resume.model_validate(_plain(root))
    except ValidationError as exc:
        errors = []
        for err in exc.errors():
            line, column = locate(root, err["loc"])
            path = ".".join(str(p) for p in err["loc"])
            errors.append({"line": line, "column": column, "message": f"{path}: {friendly_message(err)}"})
        raise ResumeInvalid(errors) from exc


def locate(root, loc):
    """Find the line/column of a validation error path inside a ruamel document."""
    node, line, column = root, None, None
    for part in loc:
        try:
            if isinstance(node, CommentedMap) and part in node:
                line, column = node.lc.key(part)
                node = node[part]
            elif isinstance(node, CommentedSeq) and isinstance(part, int) and part < len(node):
                line, column = node.lc.item(part)
                node = node[part]
            else:
                break
        except (KeyError, IndexError, AttributeError, TypeError):
            break
    return (line + 1 if line is not None else None, column + 1 if column is not None else None)


def save_raw(text, etag=None):
    parse_raw(text)
    _check_etag(etag)
    if not text.endswith("\n"):
        text += "\n"
    backup_id = backup_current("raw") if text != read_text() else None
    atomic_write_text(RESUME_PATH, text)
    return etag_for(text), backup_id


def restore(backup_id):
    text = read_backup(backup_id)
    parse_raw(text)
    backup_current("restore")
    atomic_write_text(RESUME_PATH, text)
    return etag_for(text)


def summary():
    resume, etag, warnings = load()
    return {"data": to_plain(resume), "etag": etag, "warnings": warnings, "empty": is_empty(resume)}
