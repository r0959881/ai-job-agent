from datetime import date

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

import agent_settings
import user_scope
from agent_log import log
from config import OUTPUT_DIR, PROJECT_ROOT, file_name_slug, load_resume_file, long_path


ROLE_LETTERS = {
    "Data Integration": {
        "opening": "I am writing to express my interest in Data Integration opportunities. My experience combines ETL and ELT development, SQL data preparation, source-system integration, data quality, and reporting delivery.",
        "evidence": "In my project work, I integrated IoT sensor and fleet API data into Delta Lake, unified five source systems into Medallion data layers, and designed a Python, MySQL, and Power BI solution under GDPR requirements. I also transformed a 12-week manual reporting workflow into a single-click Power BI and Power Automate solution.",
        "fit": "I would bring a practical understanding of how reliable ingestion, modelling, validation, and reporting work together. I am comfortable working across technical and business teams, documenting data definitions, and translating requirements into useful data solutions.",
        "closing": "I would welcome the opportunity to discuss how my ETL, SQL, cloud data, and data quality experience could support your integration initiatives.",
    },
    "Data Science": {
        "opening": "I am writing to express my interest in Data Science opportunities. My background combines Python, statistical analysis, machine learning, data preparation, visualization, and practical data engineering experience.",
        "evidence": "My project work includes Random Forest analysis of climate and crop-production data, a housing-price prediction pipeline with an R2 of 0.817 on unseen data, Auckland cycling-demand forecasting with Facebook Prophet, fraud detection, and a computer-vision project. Alongside this, I have built reporting pipelines and Power BI dashboards using Databricks and Microsoft Fabric.",
        "fit": "These projects have strengthened my ability to prepare data carefully, evaluate models, interpret results, and communicate findings clearly. My professional experience also taught me to connect analytical work to stakeholder requirements and decision-ready reporting.",
        "closing": "I would welcome the opportunity to discuss how my analytical foundation, curiosity, and hands-on project experience could contribute to your data science team.",
    },
    "Data Engineer": {
        "opening": "I am writing to express my interest in Data Engineering opportunities. I have practical experience with Azure Databricks, PySpark, Delta Lake, Microsoft Fabric, ETL and ELT pipelines, data quality, and CI/CD.",
        "evidence": "I built a pipeline that ingested more than 50,000 daily IoT sensor and fleet API records into Delta Lake, unified five source systems into Medallion data layers, and implemented automated data quality checks. I also created GitHub Actions pipelines for PySpark testing and infrastructure-as-code scripts that reduced manual setup time by 80 percent.",
        "fit": "I enjoy building data platforms that are reliable, observable, and useful to the people who depend on them. My experience collaborating with stakeholders helps me connect technical implementation with clear business requirements and measurable outcomes.",
        "closing": "I would welcome the opportunity to discuss how my cloud data platform, pipeline, and automation experience could support your engineering team.",
    },
    "Data Analyst": {
        "opening": "I am writing to express my interest in Data Analyst opportunities. My experience combines SQL, Power BI, DAX, KPI development, data modelling, reporting automation, and stakeholder communication.",
        "evidence": "I designed interactive Power BI dashboards for more than 50 business users, wrote SQL queries to clean and shape operational data, and translated stakeholder requirements into KPI definitions and reporting roadmaps. I also modelled organizational data and presented executive KPI dashboards directly to the CEO.",
        "fit": "I focus on making complex information understandable and actionable. From improving a 12-week manual reporting process to documenting metric logic and business use cases, I have learned to combine technical accuracy with clear communication and user adoption.",
        "closing": "I would welcome the opportunity to discuss how my analytical, reporting, and stakeholder-facing experience could contribute to your team.",
    },
    "Functional Analyst (IT)": {
        "opening": "I am writing to express my interest in Functional Analyst opportunities in IT. My experience includes requirements gathering, functional specifications, user stories, stakeholder alignment, reporting solutions, and process improvement.",
        "evidence": "At Estée Lauder Companies, I translated strategic goals into functional specifications, user stories, KPI definitions, and reporting roadmaps. I worked as a liaison between business and technical teams, guided users through iterative reviews, and helped deliver a single-click Power BI and Power Automate solution that replaced a 12-week manual workflow.",
        "fit": "I am comfortable asking clarifying questions, documenting processes and data definitions, and keeping delivery connected to the needs of users. My technical foundation in SQL, Python, Power BI, and data platforms also helps me communicate effectively with engineering teams.",
        "closing": "I would welcome the opportunity to discuss how my functional analysis, data, and stakeholder-management experience could support your IT initiatives.",
    },
}


GENERAL_LETTER = {
    "opening": "I am writing to express my interest in this opportunity. My background combines hands-on data work, clear communication, and a practical focus on useful outcomes.",
    "evidence": "My experience and projects are summarised in the attached CV, and I would be glad to walk you through the work that is most relevant to this role.",
    "fit": "I enjoy learning quickly, collaborating with both technical and business colleagues, and turning requirements into reliable results.",
    "closing": "I would welcome the opportunity to discuss how I could contribute to your team.",
}


def role_letters():
    """Editable letters from the settings, falling back to the built-in text.

    The built-in letters describe this project's original owner, so web users only
    get their own letters plus the general one.
    """
    configured = agent_settings.get("cover_letters") or {}
    builtin = {} if user_scope.current() else ROLE_LETTERS
    return {**builtin, **configured}


def _safe(text):
    return "".join(character for character in str(text) if character.isalnum() or character in " _-").strip()


def cover_letter_stem(full_name, role_family, company=None, job_title=None):
    prefix = f"{file_name_slug(full_name)}_Cover_Letter_"
    if company:
        return f"{prefix}{_safe(company)}_{_safe(job_title or role_family)}"[:180].rstrip(" ._")
    return f"{prefix}{_safe(role_family)}"


def create_cover_letter_docx(role_family, company=None, job_title=None, data=None, output_path=None):
    """Build a cover letter for a role family, optionally addressed to one job."""
    letters = role_letters()
    if role_family not in letters and not company:
        raise ValueError(f"Unknown role family: {role_family}")

    data = data if data is not None else load_resume_file() or {}

    info = data.get("personal_info", {})
    role_profile = data.get("role_profiles", {}).get(role_family, {})
    letter = letters.get(role_family, GENERAL_LETTER)
    doc = Document()
    navy = RGBColor(31, 62, 99)
    grey = RGBColor(80, 80, 80)
    font_name = "Times New Roman"

    for section in doc.sections:
        section.top_margin = Inches(0.7)
        section.bottom_margin = Inches(0.7)
        section.left_margin = Inches(0.8)
        section.right_margin = Inches(0.8)

    normal = doc.styles["Normal"]
    normal.font.name = font_name
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), font_name)
    normal.font.size = Pt(11)

    def style_run(run, size=11, bold=False, italic=False, color=None):
        run.font.name = font_name
        run._element.rPr.rFonts.set(qn("w:eastAsia"), font_name)
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.italic = italic
        if color:
            run.font.color.rgb = color

    def add_rule(paragraph):
        p_pr = paragraph._p.get_or_add_pPr()
        borders = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "6")
        bottom.set(qn("w:space"), "3")
        bottom.set(qn("w:color"), "B7B7B7")
        borders.append(bottom)
        p_pr.append(borders)

    name = doc.add_paragraph()
    name.paragraph_format.space_after = Pt(1)
    style_run(name.add_run((info.get("full_name") or "").upper()), size=19, bold=True, color=navy)

    contact = doc.add_paragraph()
    contact.paragraph_format.space_after = Pt(12)
    contact_parts = [info.get("location"), info.get("phone"), info.get("email"), info.get("work_authorization")]
    style_run(contact.add_run(info.get("headline", "")), size=10.5)
    contact.add_run("\n")
    style_run(contact.add_run(" | ".join(part for part in contact_parts if part)), size=9.5, color=grey)

    date_paragraph = doc.add_paragraph()
    date_paragraph.paragraph_format.space_after = Pt(14)
    style_run(date_paragraph.add_run(date.today().strftime("%d %B %Y")), size=10.5)

    recipient = doc.add_paragraph()
    recipient.paragraph_format.space_after = Pt(12)
    style_run(recipient.add_run("Hiring Manager\n"), size=11, bold=True)
    style_run(recipient.add_run(f"{company}\n" if company else "[Company Name]\n[Company Address]"), size=11, color=grey)

    subject = doc.add_paragraph()
    subject.paragraph_format.space_after = Pt(14)
    subject_role = job_title or f"{role_family} role"
    style_run(subject.add_run(f"Subject: Application for {subject_role}"), size=11, bold=True, color=navy)

    paragraphs = [
        f"Dear Hiring Manager,\n\n{letter['opening']}",
        letter["evidence"],
        f"My focus is on {role_profile.get('focus', 'turning reliable data into useful outcomes')}. {letter['fit']}",
        letter["closing"],
    ]
    for text in paragraphs:
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(10)
        paragraph.paragraph_format.line_spacing = 1.08
        style_run(paragraph.add_run(text), size=11)

    closing = doc.add_paragraph()
    closing.paragraph_format.space_before = Pt(4)
    style_run(closing.add_run("Kind regards,\n"), size=11)
    style_run(closing.add_run(info.get("full_name") or ""), size=11, bold=True, color=navy)

    if output_path:
        doc.save(output_path)
        return str(output_path)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = cover_letter_stem(info.get("full_name"), role_family, company, job_title)
    path = f"output/{stem}.docx"
    doc.save(long_path(PROJECT_ROOT / path))
    log(f"Cover letter created: {path}")
    return path


if __name__ == "__main__":
    for role in role_letters():
        create_cover_letter_docx(role)
