"""What the Apply workspace shows next to a job: keyword match against the resume and tips per source."""
import re


def _words_in(text, keyword):
    return re.search(rf"(?<![\w]){re.escape(keyword.lower())}(?![\w])", text) is not None


def keyword_match(job, resume):
    """Resume keywords found in the posting, and the role keywords it does not mention."""
    text = f"{job.get('title', '')} {job.get('description', '')}".lower()
    profile = (resume.get("role_profiles") or {}).get(job.get("role_family") or "", {})
    role_keywords = list(profile.get("keywords") or [])
    skills = [skill for skills in (resume.get("core_skills") or {}).values() for skill in skills]
    candidates: list[str] = []
    for keyword in role_keywords + skills:
        short = re.sub(r"\s*\(.*?\)", "", keyword).strip()
        if short and short.lower() not in {c.lower() for c in candidates}:
            candidates.append(short)
    matched = [k for k in candidates if _words_in(text, k)]
    missing = [k for k in role_keywords if not _words_in(text, re.sub(r"\s*\(.*?\)", "", k).strip())]
    return matched, missing


def source_tips(job):
    source = (job.get("source") or "").lower()
    tips = []
    if "linkedin" in source:
        tips.append("LinkedIn links open LinkedIn: sign in first. “Easy Apply” means you upload your CV "
                    "in LinkedIn's own dialog, so download the tailored CV below first.")
    if "indeed" in source:
        tips.append("Indeed may ask you to sign in. “Easily apply” uses Indeed's form: upload the tailored CV there.")
    if "adzuna" in source:
        tips.append("Adzuna links redirect to the employer or agency site. Apply on the page you land on.")
    if "arbeitnow" in source:
        tips.append("Arbeitnow listings link to the company's careers page, which often has its own form.")
    if "stepstone" in source or "jobat" in source:
        tips.append("StepStone and Jobat usually need an account; your CV upload there can be reused for later jobs.")
    if "vdab" in source:
        tips.append("VDAB vacancies may require applying through your Mijn Loopbaan account.")
    if "michael page" in source:
        tips.append("Michael Page is a recruiter: the client company is usually named once a consultant calls you.")
    if (job.get("company") or "").startswith("Partner ("):
        tips.append("The company name was not in the listing. Open the posting to find it before you write "
                    "the cover letter.")
    return tips
