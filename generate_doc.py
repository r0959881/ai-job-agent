"""The tailored CV, as a PDF.

What recruiters screening hundreds of CVs look for, and how this file does it:
- A clean, consistent design (modelled on the owner's own Data Engineer CV): name in
  spaced capitals, a teal catch phrase, contact details in the header, spaced section
  titles over thin rules, grouped skills, square bullets, and the languages last.
- Visibly adapted to the job: the catch phrase names the company and role, the skills
  the posting asks for come first, and the job's key terms are set in bold.
- Up to two pages: only the projects that fit the role are shown (the role profile's
  preferred projects, else those the posting relates to), the PDF's pages are counted, and
  the least important content is trimmed until it fits (fewer projects, then fewer
  bullets, then shorter coursework).
- A standard font: Carlito (metrically identical to Calibri), embedded so the CV looks
  the same everywhere. It falls back to Helvetica if the font files are missing.

Tailored bullets may start with "[n]" (the experience entry they rewrite, 1-based)
and may mark terms with **double asterisks** for bold.
"""
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Flowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from agent_log import log
from config import CODE_ROOT, OUTPUT_DIR, PROJECT_ROOT, document_stem, file_name_slug, load_resume_file, long_path

NAVY = colors.HexColor("#1F3A5F")
TEAL = colors.HexColor("#1E7A93")
MUTED = colors.HexColor("#5B6573")
RULE = colors.HexColor("#C9D2DC")
TEXT = colors.HexColor("#1F2328")

MARGIN = 15 * mm
MAX_PAGES = 2
MAX_BULLETS_PER_ROLE = 4
MAX_PROJECTS = 8
MAX_SKILL_GROUPS = 5
MAX_CERTIFICATIONS = 4
MAX_COURSES = 7

_TAG = re.compile(r"^\s*\[(\d+)\]\s*")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
FONT_DIR = CODE_ROOT / "fonts"


def _register_fonts():
    files = {"Carlito": "Carlito-Regular.ttf", "Carlito-Bold": "Carlito-Bold.ttf",
             "Carlito-Italic": "Carlito-Italic.ttf", "Carlito-BoldItalic": "Carlito-BoldItalic.ttf"}
    try:
        for name, file in files.items():
            if name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / file)))
        pdfmetrics.registerFontFamily("Carlito", normal="Carlito", bold="Carlito-Bold", italic="Carlito-Italic",
                                      boldItalic="Carlito-BoldItalic")
        return "Carlito", "Carlito-Bold", "Carlito-Italic"
    except Exception:  # a missing font file must not stop CVs from being made
        return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"


FONT, FONT_BOLD, FONT_ITALIC = _register_fonts()
# Carlito draws a neat square bullet like the owner's CV; Helvetica (fallback) does not have one.
BULLET = "▪" if FONT == "Carlito" else "•"


def cv_filename_prefix(full_name=None):
    return f"{file_name_slug(full_name)}_CV_"


def cv_file_stem(_full_name, company_name, job_title):
    """'Data Engineer_Acme_CV': the cleaned job title, the company and the CV key."""
    return document_stem(job_title, company_name, "cv")


# --------------------------------------------------------------------------- content plan

def _words(text):
    return set(re.findall(r"[a-z0-9+#.]+", (text or "").lower()))


def _short(keyword):
    return re.sub(r"\s*\(.*?\)", "", str(keyword)).strip()


def _mentions(text, keyword):
    keyword = _short(keyword)
    return bool(keyword) and re.search(rf"(?<![\w]){re.escape(keyword.lower())}(?![\w])", text) is not None


def plain(text):
    """Text without the **bold** markers."""
    return _BOLD.sub(r"\1", str(text or ""))


def split_tag(bullet):
    """'[2] Built X' -> (1, 'Built X'): the 0-based experience index it belongs to, or None."""
    text = str(bullet or "")
    match = _TAG.match(text)
    if not match:
        return None, text.strip()
    rest = text[match.end():]
    while _TAG.match(rest):  # a model sometimes repeats the tag: never print "[1]" on the CV
        rest = rest[_TAG.match(rest).end():]
    return int(match.group(1)) - 1, rest.strip()


def highlight_terms(data, role_profile, job_text, extra=()):
    """Resume skills and role keywords that the job posting mentions: these are set in bold."""
    text = (job_text or "").lower()
    candidates = list(role_profile.get("keywords") or []) + list(extra)
    for skills in (data.get("core_skills") or {}).values():
        candidates += list(skills if isinstance(skills, list) else [skills])
    terms = []
    for keyword in candidates:
        short = _short(keyword)
        if short and len(short) > 1 and _mentions(text, short) and short.lower() not in {t.lower() for t in terms}:
            terms.append(short)
    return sorted(terms, key=len, reverse=True)  # longest first, so "Power BI" wins over "BI"


def _score(text, job_words):
    return len(_words(text) & job_words)


ACRONYMS = {"etl": "ETL", "elt": "ELT", "bi": "BI", "devops": "DevOps", "ml": "ML", "ai": "AI", "sql": "SQL",
            "api": "API", "apis": "APIs", "ci/cd": "CI/CD", "it": "IT", "ux": "UX"}


def _label(category):
    """'engineering_and_etl' -> 'Engineering and ETL'."""
    words = str(category).replace("_", " ").split()
    words = [ACRONYMS.get(w.lower(), w.lower()) for w in words]
    if words and words[0] == words[0].lower():
        words[0] = words[0].capitalize()
    return " ".join(words)


@dataclass
class Plan:
    tagline: str
    summary: str
    skills: list  # the skills to lead with
    skill_groups: list  # [(label, [skills])]
    experience: list  # [(entry, [bullets])]
    projects: list  # [(project, [highlights])]
    education: list  # [(entry, [courses])]
    certifications: list
    languages: list
    bold_terms: list = field(default_factory=list)


def _pool(data):
    pool = []
    for skills in (data.get("core_skills") or {}).values():
        pool += [str(s) for s in (skills if isinstance(skills, list) else [skills])]
    return pool


def _lead_skills(data, chosen, job_text):
    """The AI's pick (only skills really in the resume), else the resume skills the posting mentions."""
    pool = _pool(data)
    if chosen:
        known = {s.lower(): s for s in pool} | {_short(s).lower(): s for s in pool}
        picked = [known.get(str(s).lower()) or known.get(_short(s).lower()) for s in chosen]
        picked = list(dict.fromkeys(s for s in picked if s))
        if len(picked) >= 4:
            return picked
    text = (job_text or "").lower()
    matched = [s for s in pool if _mentions(text, s)]
    return list(dict.fromkeys(matched + [s for s in pool if s not in matched]))


def _skill_groups(data, role_profile, lead):
    """Skill categories as 'Label: a, b, c' lines, the most relevant categories and skills first."""
    categories = {k: [str(s) for s in (v if isinstance(v, list) else [v])]
                  for k, v in (data.get("core_skills") or {}).items()}
    rank = {skill: index for index, skill in enumerate(lead)}
    preferred = [c for c in role_profile.get("preferred_skill_categories") or [] if c in categories]

    def relevance(name):
        hits = [rank[s] for s in categories[name] if s in rank]
        return (0 if name in preferred else 1, min(hits) if hits else 999, -len(hits))

    groups = []
    for name in sorted(categories, key=relevance)[:MAX_SKILL_GROUPS]:
        skills = sorted(categories[name], key=lambda s: rank.get(s, 999))
        if skills:
            groups.append((_label(name), skills))
    return groups


def _education(data):
    education = data.get("education") or []
    return [education] if isinstance(education, dict) else [e for e in education if isinstance(e, dict)]


def build_plan(data, role_family, summary, bullets, tagline="", skills=None, job_title="", company="",
               job_text=""):
    """Decide what goes on the page, before any drawing."""
    info = data.get("personal_info") or {}
    role_profile = (data.get("role_profiles") or {}).get(role_family or "", {}) or {}
    job_words = _words(f"{job_title} {job_text}") or _words(" ".join(role_profile.get("keywords") or []))

    tailored, untagged = {}, []
    for bullet in bullets or []:
        index, text = split_tag(bullet)
        if text:
            (tailored.setdefault(index, []) if index is not None else untagged).append(text)
    experience = []
    entries = [e for e in data.get("experience") or [] if isinstance(e, dict)]
    for index, entry in enumerate(entries):
        own = tailored.get(index) or []
        if not own and index == 0 and untagged:  # older content: put untagged highlights on the latest role
            own = untagged
        originals = sorted(entry.get("bullets") or [], key=lambda b: _score(b, job_words), reverse=True)
        experience.append((entry, (own or originals)[:MAX_BULLETS_PER_ROLE]))

    # Only the projects that fit the role: the role profile's preferred ones in its order, else the
    # projects the job posting relates to, most relevant first.
    projects = [p for p in data.get("projects") or [] if isinstance(p, dict)]
    by_title = {p.get("title"): p for p in projects}
    preferred = [by_title[t] for t in role_profile.get("preferred_projects") or [] if t in by_title]
    if not preferred:
        scored = [(_score(" ".join([p.get("title", ""), p.get("tech_stack", ""), *(p.get("highlights") or [])]),
                          job_words), p) for p in projects]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        preferred = [p for score, p in scored if score > 0][:MAX_PROJECTS] or [p for _s, p in scored[:2]]
    project_plan = [(project, list(project.get("highlights") or [])[:2]) for project in preferred[:MAX_PROJECTS]]

    education = []
    for entry in _education(data):
        courses = sorted(entry.get("coursework") or [], key=lambda c: _score(c, job_words), reverse=True)
        education.append((entry, courses[:MAX_COURSES]))

    certifications = []
    for cert in data.get("certifications") or []:
        if isinstance(cert, dict):
            details = ", ".join(str(x) for x in (cert.get("issuer"), cert.get("year")) if x)
            certifications.append(f"{cert.get('name', '')}" + (f" — {details}" if details else ""))
        elif cert:
            certifications.append(str(cert))

    # Without a tailored catch phrase the headline is used: job-alert titles and "Partner (...)"
    # company names are too messy to build one from.
    tagline = tagline or info.get("headline") or ""
    lead = _lead_skills(data, skills, f"{job_title} {job_text}")
    return Plan(
        tagline=plain(tagline).strip(),
        summary=str(summary or "").strip(),
        skills=lead[:12],
        skill_groups=_skill_groups(data, role_profile, lead),
        experience=experience,
        projects=project_plan,
        education=education,
        certifications=certifications[:MAX_CERTIFICATIONS],
        languages=[str(lang) for lang in data.get("languages") or [] if lang],
        bold_terms=highlight_terms(data, role_profile, f"{job_title} {job_text}", extra=lead[:12]),
    )


# Trimming, least important first, until the PDF fits MAX_PAGES.
def _trim_projects(plan, keep=None, keep_highlights=None):
    if keep is not None:
        plan.projects = plan.projects[:keep]
    if keep_highlights is not None:
        plan.projects = [(p, h[:keep_highlights]) for p, h in plan.projects]


def _trim_bullets(plan, keep, older_only=False):
    plan.experience = [(e, b if (older_only and i == 0) else b[:keep]) for i, (e, b) in enumerate(plan.experience)]


TRIM_STEPS = [
    lambda p: _trim_projects(p, keep_highlights=1),
    lambda p: _trim_projects(p, keep=6),
    lambda p: setattr(p, "education", [(e, c[:4]) for e, c in p.education]),
    lambda p: _trim_projects(p, keep=4),
    lambda p: _trim_projects(p, keep=3),
    lambda p: _trim_bullets(p, 3),
    lambda p: setattr(p, "skill_groups", p.skill_groups[:4]),
    lambda p: _trim_projects(p, keep=2),
    lambda p: _trim_bullets(p, 2, older_only=True),
    lambda p: setattr(p, "certifications", p.certifications[:2]),
    lambda p: setattr(p, "education", [(e, []) for e, _c in p.education]),
    lambda p: _trim_projects(p, keep=1),
    lambda p: _trim_bullets(p, 2),
    lambda p: setattr(p, "skill_groups", p.skill_groups[:3]),
]


# ------------------------------------------------------------------------------- drawing

def _style(name, size=10, leading=None, font=None, color=TEXT, **extra):
    return ParagraphStyle(name, fontName=font or FONT, fontSize=size, leading=leading or size * 1.28,
                          textColor=color, **extra)


STYLES = {
    "tagline": _style("tagline", 12.5, 16, color=TEAL),
    "contact": _style("contact", 9.5, 12.5, color=MUTED),
    "body": _style("body", 10, 13.2),
    "skill": _style("skill", 10, 13, spaceAfter=2.5),
    "role": _style("role", 10.8, 13.5, font=FONT_BOLD),
    "dates": _style("dates", 9.5, 13.5, color=MUTED, alignment=TA_RIGHT),
    "place": _style("place", 9.8, 12.8, font=FONT_ITALIC, color=TEAL, spaceAfter=2),
    "bullet": _style("bullet", 10, 13, leftIndent=12, bulletIndent=1.5, spaceAfter=1.8, bulletFontName=FONT,
                     bulletFontSize=9, bulletColor=TEAL),
    "project": _style("project", 10.4, 13.5, font=FONT_BOLD, spaceBefore=2),
}


# Characters the font lacks that language models like to write, mapped to ones it has.
_REPLACE = str.maketrans({"\u2011": "-", "\u2010": "-", "\u00a0": " ", "\u202f": " ", "\u2009": " ", "\u200b": ""})


def rich(text, terms=(), max_auto_bold=3):
    """Escape text for a Paragraph; **marked** terms become bold, plus a few of the job's terms."""
    text = str(text or "").translate(_REPLACE)
    if not _BOLD.search(text) and terms:
        bolded = 0
        for term in terms:
            if bolded >= max_auto_bold:
                break
            pattern = re.compile(rf"(?<![\w*])({re.escape(term)})(?![\w*])", re.IGNORECASE)
            if pattern.search(text):
                text = pattern.sub(r"**\1**", text, count=1)
                bolded += 1
    parts = _BOLD.split(text)
    return "".join(f"<b>{escape(part)}</b>" if index % 2 else escape(part) for index, part in enumerate(parts))


class SpacedText(Flowable):
    """A line of letter-spaced capitals (the name and section titles), optionally over a rule."""

    def __init__(self, text, size, color, space=1.2, rule=None, rule_width=0.6, gap=3.5):
        super().__init__()
        self.text, self.size, self.color, self.space = text.upper(), size, color, space
        self.rule, self.rule_width, self.gap = rule, rule_width, gap

    def wrap(self, avail_width, avail_height):
        self.width = avail_width
        self.height = self.size + (self.gap + self.rule_width if self.rule else 0)
        return self.width, self.height

    def draw(self):
        canvas = self.canv
        text = canvas.beginText()
        text.setFont(FONT_BOLD, self.size)
        text.setCharSpace(self.space)
        text.setFillColor(self.color)
        text.setTextOrigin(0, self.height - self.size * 0.82)
        text.textOut(self.text)
        canvas.drawText(text)
        if self.rule:
            canvas.setStrokeColor(self.rule)
            canvas.setLineWidth(self.rule_width)
            canvas.line(0, self.rule_width / 2, self.width, self.rule_width / 2)


class Rule(Flowable):
    def __init__(self, color=NAVY, width=2.2, before=4, after=8):
        super().__init__()
        self.color, self.line_width, self.before, self.after = color, width, before, after

    def wrap(self, avail_width, avail_height):
        self.width = avail_width
        return avail_width, self.before + self.line_width + self.after

    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.line_width)
        y = self.after + self.line_width / 2
        self.canv.line(0, y, self.width, y)


def _heading(text):
    return [Spacer(1, 9), SpacedText(text, 11, NAVY, space=1.1, rule=RULE), Spacer(1, 5)]


def _two_columns(left, right, width, style_left="role"):
    table = Table([[Paragraph(left, STYLES[style_left]), Paragraph(escape(right or ""), STYLES["dates"])]],
                  colWidths=[width * 0.76, width * 0.24], hAlign="LEFT")
    table.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                               ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                               ("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
    return table


def _bullet(text, terms):
    return Paragraph(rich(text, terms), STYLES["bullet"], bulletText=BULLET)


def _contact_line(info):
    items = [escape(str(info[key])) for key in ("location", "phone") if info.get(key)]
    if info.get("email"):
        email = escape(str(info["email"]))
        items.append(f'<a href="mailto:{email}" color="#5B6573">{email}</a>')
    for key in ("linkedin", "github", "website", "portfolio"):
        value = str(info.get(key) or "").strip()
        if value:
            url = value if value.startswith("http") else f"https://{value}"
            label = re.sub(r"^https?://(www\.)?", "", value).rstrip("/")
            items.append(f'<a href="{escape(url)}" color="#5B6573">{escape(label)}</a>')
    return "  •  ".join(items)


def story(plan, info, width):
    terms = plan.bold_terms
    parts = [SpacedText(info.get("full_name") or "", 25, NAVY, space=1.6), Spacer(1, 6)]
    if plan.tagline:
        parts.append(Paragraph(rich(plain(plan.tagline)), STYLES["tagline"]))
    parts.append(Paragraph(_contact_line(info), STYLES["contact"]))
    authorization = info.get("work_status") or info.get("work_authorization")
    if authorization:
        parts.append(Paragraph(f'<font name="{FONT_BOLD}" color="#1F3A5F">Work authorisation:</font> '
                               f'{escape(str(authorization))}', STYLES["contact"]))
    parts.append(Rule())

    if plan.summary:
        parts += _heading("Professional summary")
        parts.append(Paragraph(rich(plan.summary, terms, max_auto_bold=4), STYLES["body"]))

    if plan.skill_groups:
        parts += _heading("Key skills")
        lead = {_short(s).lower() for s in plan.skills} | {t.lower() for t in terms}
        for label, skills in plan.skill_groups:
            shown = [f"<b>{escape(s)}</b>" if _short(s).lower() in lead else escape(s) for s in skills]
            parts.append(Paragraph(f'<font name="{FONT_BOLD}" color="#1F3A5F">{escape(label)}:</font> '
                                   + ", ".join(shown), STYLES["skill"]))

    if plan.experience:
        parts += _heading("Professional experience")
        for index, (entry, bullets) in enumerate(plan.experience):
            place = "  |  ".join(escape(str(x)) for x in (entry.get("company"), entry.get("location")) if x)
            block = [Spacer(1, 3 if index else 0),
                     _two_columns(escape(entry.get("role", "")), entry.get("dates", ""), width)]
            if place:
                block.append(Paragraph(place, STYLES["place"]))
            parts.append(KeepTogether(block + [_bullet(b, terms) for b in bullets[:1]]))
            parts += [_bullet(b, terms) for b in bullets[1:]]

    if plan.projects:
        parts += _heading("Projects")
        for project, highlights in plan.projects:
            tech = escape(str(project.get("tech_stack") or "")).replace(", ", " · ")
            title = (f'{escape(project.get("title", ""))}  <font name="{FONT_ITALIC}" size="9" color="#5B6573">'
                     f"{tech}</font>")
            parts.append(KeepTogether([Paragraph(title, STYLES["project"])] + [_bullet(h, terms) for h in highlights]))

    if plan.education:
        parts += _heading("Education")
        for entry, courses in plan.education:
            block = [_two_columns(escape(entry.get("degree", "")), entry.get("dates") or entry.get("year") or "",
                                  width)]
            place = "  |  ".join(escape(str(x)) for x in (entry.get("institution"), entry.get("location")) if x)
            if place:
                block.append(Paragraph(place, STYLES["place"]))
            if courses:
                block.append(Paragraph(f"Coursework: {rich(', '.join(courses), terms)}", STYLES["body"]))
            parts.append(KeepTogether(block))

    if plan.certifications:
        parts += _heading("Certifications")
        parts += [_bullet(cert, terms) for cert in plan.certifications]

    if plan.languages:
        parts += [Spacer(1, 10), Paragraph(
            f'<font name="{FONT_BOLD}" color="#1F3A5F">Languages:</font> ' + escape(" • ".join(plan.languages)),
            STYLES["body"])]
    return parts


def render_pdf(plan, info, title=""):
    """(pdf bytes, page count)."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=13 * mm,
                            bottomMargin=12 * mm, title=title, author=info.get("full_name") or "",
                            subject="Curriculum vitae", creator="AI Job Agent")
    # Flowables get the frame width minus its 6 pt padding on each side.
    doc.build(story(plan, info, doc.width - 12))
    return buffer.getvalue(), doc.page


def build_cv_pdf(data, company_name, job_title, summary, bullets, role_family=None, tagline="", skills=None,
                 job_text=""):
    """The CV as PDF bytes, trimmed until it fits MAX_PAGES."""
    info = data.get("personal_info") or {}
    plan = build_plan(data, role_family, summary, bullets, tagline=tagline, skills=skills, job_title=job_title,
                      company=company_name, job_text=job_text)
    title = f"{info.get('full_name') or 'CV'} — {job_title}".strip(" —")
    pdf, pages = render_pdf(plan, info, title)
    for step in TRIM_STEPS:
        if pages <= MAX_PAGES:
            break
        step(plan)
        pdf, pages = render_pdf(plan, info, title)
    return pdf


def create_tailored_cv(company_name, job_title, tailored_summary, tailored_bullets, role_family=None,
                       data=None, output_path=None, tagline="", skills=None, job_text=""):
    """Write the tailored CV as a PDF.

    `data` overrides resume_data.yaml (used for previews of unsaved edits) and
    `output_path` (a path or a file-like object) overrides the output/ file name.
    `job_text` is the posting, used to pick and bold what matters for this job.
    """
    if data is None:
        data = load_resume_file()
        if data is None:
            log("❌ Error: resume_data.yaml not found!", level="error")
            return None
    pdf = build_cv_pdf(data, company_name, job_title, tailored_summary, tailored_bullets, role_family,
                       tagline=tagline, skills=skills, job_text=job_text)
    if output_path is not None and hasattr(output_path, "write"):
        output_path.write(pdf)
        return output_path
    if output_path:
        Path(output_path).write_bytes(pdf)
        return str(output_path)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    info = data.get("personal_info") or {}
    file_path = f"output/{cv_file_stem(info.get('full_name'), company_name, job_title)}.pdf"
    Path(long_path(PROJECT_ROOT / file_path)).write_bytes(pdf)
    log(f"📄 CV created: {file_path}")
    return file_path


if __name__ == "__main__":
    sample_summary = ("Data engineer who builds **Databricks** and **Microsoft Fabric** pipelines and turns them "
                      "into Power BI reporting that business teams use every day.")
    sample_bullets = ["[1] Built a **PySpark** ETL pipeline that loads >50K IoT records a day into Delta Lake."]
    print(create_tailored_cv("Algo1", "Data Engineer", sample_summary, sample_bullets, "Data Engineer",
                             tagline="Data Engineer for Algo1's platform team", job_text="Databricks PySpark SQL"))
