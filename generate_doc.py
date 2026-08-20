import os
import yaml
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

def create_tailored_cv_docx(company_name, job_title, tailored_summary, tailored_bullets):
    """Generates a professional .docx CV formatted for ATS parsers."""
    
    # Load master profile info
    if not os.path.exists("resume_data.yaml"):
        print("❌ Error: resume_data.yaml not found!")
        return None

    with open("resume_data.yaml", "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
        
    info = data.get("personal_info", {})
    doc = Document()
    
    # Set page margins (0.5 inch / clean margins)
    sections = doc.sections
    for section in sections:
        section.top_margin = Inches(0.5)
        section.bottom_margin = Inches(0.5)
        section.left_margin = Inches(0.6)
        section.right_margin = Inches(0.6)
        
    # --- HEADER ---
    title_p = doc.add_paragraph()
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_name = title_p.add_run(info.get("full_name", "Ammar Haider").upper())
    run_name.font.size = Pt(18)
    run_name.font.bold = True
    run_name.font.color.rgb = RGBColor(31, 78, 121) # Professional Navy
    
    contact_p = doc.add_paragraph()
    contact_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Build contact string safely without KeyError
    contact_parts = [
        info.get("location"),
        info.get("phone"),
        info.get("email"),
        info.get("work_status") or info.get("work_authorization")
    ]
    contact_str = " | ".join([part for part in contact_parts if part])
    
    run_contact = contact_p.add_run(contact_str)
    run_contact.font.size = Pt(9.5)
    
    # Helper to add section headings
    def add_heading(text):
        h = doc.add_paragraph()
        h.paragraph_format.space_before = Pt(10)
        h.paragraph_format.space_after = Pt(3)
        run = h.add_run(text.upper())
        run.font.size = Pt(11)
        run.font.bold = True
        run.font.color.rgb = RGBColor(31, 78, 121)
        
    # --- PROFESSIONAL SUMMARY ---
    add_heading("Professional Summary")
    p_sum = doc.add_paragraph()
    p_sum.paragraph_format.space_after = Pt(6)
    p_sum.add_run(tailored_summary).font.size = Pt(10)

    # --- CORE SKILLS ---
    add_heading("Technical Skills & Core Competencies")
    skills = data.get("core_skills", {})
    if isinstance(skills, dict):
        for category, skill_list in skills.items():
            p_sk = doc.add_paragraph()
            p_sk.paragraph_format.space_after = Pt(2)
            r_cat = p_sk.add_run(f"• {category.replace('_', ' ').title()}: ")
            r_cat.font.bold = True
            r_cat.font.size = Pt(9.5)
            p_sk.add_run(", ".join(skill_list) if isinstance(skill_list, list) else str(skill_list)).font.size = Pt(9.5)
    elif isinstance(skills, list):
        p_sk = doc.add_paragraph()
        p_sk.add_run("• Skills: " + ", ".join(skills)).font.size = Pt(9.5)

    # --- PROFESSIONAL EXPERIENCE ---
    add_heading("Professional Experience")
    
    if tailored_bullets:
        p_tb_head = doc.add_paragraph()
        r_tb = p_tb_head.add_run("Key Role-Matched Highlights:")
        r_tb.font.bold = True
        r_tb.font.size = Pt(9.5)
        for bullet in tailored_bullets:
            p_b = doc.add_paragraph(style='List Bullet')
            p_b.paragraph_format.space_after = Pt(2)
            p_b.add_run(bullet).font.size = Pt(9.5)

    for exp in data.get("experience", []):
        p_exp = doc.add_paragraph()
        p_exp.paragraph_format.space_before = Pt(4)
        p_exp.paragraph_format.space_after = Pt(2)
        
        r_role = p_exp.add_run(f"{exp.get('role', '')} | {exp.get('company', '')}")
        r_role.font.bold = True
        r_role.font.size = Pt(10)
        
        r_date = p_exp.add_run(f" ({exp.get('dates', '')})")
        r_date.font.italic = True
        r_date.font.size = Pt(9.5)
        
        for bullet in exp.get("bullets", []):
            p_b = doc.add_paragraph(style='List Bullet')
            p_b.paragraph_format.space_after = Pt(2)
            p_b.add_run(bullet).font.size = Pt(9.5)

    # --- EDUCATION & CERTIFICATIONS ---
    add_heading("Education & Certifications")
    edu = data.get("education", {})
    p_edu = doc.add_paragraph()
    p_edu.paragraph_format.space_after = Pt(2)
    
    if isinstance(edu, dict):
        p_edu.add_run(f"• {edu.get('degree', '')} — {edu.get('institution', '')} ({edu.get('dates', edu.get('year', ''))})").font.size = Pt(9.5)
    elif isinstance(edu, list):
        for e in edu:
            p_e = doc.add_paragraph()
            p_e.paragraph_format.space_after = Pt(2)
            p_e.add_run(f"• {e.get('degree', '')} — {e.get('institution', '')} ({e.get('year', '')})").font.size = Pt(9.5)

    for cert in data.get("certifications", []):
        p_cert = doc.add_paragraph()
        p_cert.paragraph_format.space_after = Pt(2)
        if isinstance(cert, dict):
            p_cert.add_run(f"• {cert.get('name', '')} ({cert.get('issuer', '')}, {cert.get('year', '')})").font.size = Pt(9.5)
        else:
            p_cert.add_run(f"• {cert}").font.size = Pt(9.5)

    # Save Document
    os.makedirs("output", exist_ok=True)
    clean_company = "".join(c for c in company_name if c.isalnum() or c in (' ', '_')).strip()
    clean_title = "".join(c for c in job_title if c.isalnum() or c in (' ', '_')).strip()
    
    file_path = f"output/Ammar_Haider_CV_{clean_company}_{clean_title}.docx"
    doc.save(file_path)
    print(f"📄 Word Document created successfully: {file_path}")
    return file_path

if __name__ == "__main__":
    sample_summary = "Data Engineer with proven expertise building Medallion architectures and Power BI solutions across Azure Databricks and Microsoft Fabric."
    sample_bullets = [
        "Designed and implemented a production-grade ETL pipeline that ingested >50K IoT sensor records daily into Delta Lake.",
        "Built a CI/CD framework with GitHub Actions, Docker, and Kubernetes reducing manual setup time by 80%."
    ]
    create_tailored_cv_docx("Algo1", "Software_Engineer_Platform", sample_summary, sample_bullets)