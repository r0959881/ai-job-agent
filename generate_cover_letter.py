import os
from datetime import date

import yaml
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


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


def create_cover_letter_docx(role_family):
    if role_family not in ROLE_LETTERS:
        raise ValueError(f"Unknown role family: {role_family}")

    with open("resume_data.yaml", "r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    info = data.get("personal_info", {})
    role_profile = data.get("role_profiles", {}).get(role_family, {})
    letter = ROLE_LETTERS[role_family]
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
    style_run(name.add_run(info.get("full_name", "Ammar Haider").upper()), size=19, bold=True, color=navy)

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
    style_run(recipient.add_run("[Company Name]\n[Company Address]"), size=11, color=grey)

    subject = doc.add_paragraph()
    subject.paragraph_format.space_after = Pt(14)
    style_run(subject.add_run(f"Subject: Application for {role_family} role"), size=11, bold=True, color=navy)

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
    style_run(closing.add_run(info.get("full_name", "Ammar Haider")), size=11, bold=True, color=navy)

    os.makedirs("output", exist_ok=True)
    safe_role = "".join(character for character in role_family if character.isalnum() or character in " _-").strip()
    path = f"output/Ammar_Haider_Cover_Letter_{safe_role}.docx"
    doc.save(path)
    print(f"Cover letter created: {path}")
    return path


if __name__ == "__main__":
    for role in ROLE_LETTERS:
        create_cover_letter_docx(role)
