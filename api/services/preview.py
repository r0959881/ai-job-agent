"""Render DOCX files as HTML for in-browser previews."""
import html
import re
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


def sample_cv_pdf(data, role_family=None):
    """A sample CV (PDF bytes) from (possibly unsaved) resume data, in the real CV layout."""
    from generate_doc import build_cv_pdf

    info = data.get("personal_info") or {}
    summary = (
        f"{info.get('headline') or 'Your headline'}. This is where the tailored 2-sentence summary for each job "
        "appears. The agent writes it from your resume facts for the role family you pick."
    )
    first_bullets: list[str] = []
    for index, experience in enumerate(data.get("experience") or []):
        first_bullets.extend(f"[{index + 1}] {bullet}" for bullet in (experience.get("bullets") or [])[:2])
    return build_cv_pdf(data, "Sample Company", "Sample Role", summary, first_bullets, role_family,
                        tagline=f"{info.get('headline') or 'Your catch phrase'} (adapted to each company)")
