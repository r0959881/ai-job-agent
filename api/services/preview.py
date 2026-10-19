"""Render DOCX files as HTML for in-browser previews."""
import html
import re
import tempfile
from pathlib import Path

import mammoth

from config import long_path

# mammoth only emits a small, fixed set of tags from the document text, which it
# escapes. As a second line of defence strip anything that could run script.
_DANGEROUS = re.compile(r"<\s*(script|style|iframe|object|embed)[^>]*>.*?<\s*/\s*\1\s*>", re.I | re.S)
_EVENT_ATTR = re.compile(r"\s+on[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.I)
_JS_URL = re.compile(r"(href|src)\s*=\s*([\"'])\s*javascript:[^\"']*\2", re.I)


def sanitise(markup):
    markup = _DANGEROUS.sub("", markup)
    markup = _EVENT_ATTR.sub("", markup)
    return _JS_URL.sub(r'\1="#"', markup)


def docx_to_html(path):
    with open(long_path(path), "rb") as handle:
        result = mammoth.convert_to_html(handle)
    return sanitise(result.value)


def text_preview(path, limit=200_000):
    text = Path(long_path(path)).read_text(encoding="utf-8", errors="replace")[:limit]
    return f"<pre>{html.escape(text)}</pre>"


def sample_cv_html(data, role_family=None):
    """Build a sample CV from (possibly unsaved) resume data and return it as HTML."""
    from generate_doc import create_tailored_cv_docx

    info = data.get("personal_info") or {}
    summary = (
        f"{info.get('headline') or 'Your headline'}. This is where the tailored, 3-sentence summary for each job "
        "appears. The agent writes it from your resume facts for the role family you pick."
    )
    first_bullets = []
    for experience in data.get("experience") or []:
        first_bullets.extend((experience.get("bullets") or [])[:1])
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / "preview.docx"
        create_tailored_cv_docx("Sample Company", "Sample Role", summary, first_bullets[:4], role_family,
                                data=data, output_path=target)
        return docx_to_html(target)
