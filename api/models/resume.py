"""Pydantic models that mirror resume_data.yaml exactly.

Unknown keys are kept (extra="allow") so nothing in the file is ever lost, and
numbers such as `year: 2026` are read as strings like the CV generator expects.
"""
from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Base(BaseModel):
    model_config = ConfigDict(extra="allow", coerce_numbers_to_str=True, str_strip_whitespace=False)


def _clean_list(values):
    if values is None:
        return []
    if isinstance(values, str):
        return [values]
    return [str(v) for v in values if v is not None and str(v).strip() != ""]


class PersonalInfo(_Base):
    full_name: str = ""
    headline: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""

    @field_validator("email")
    @classmethod
    def email_shape(cls, value):
        value = (value or "").strip()
        if value and ("@" not in value or "." not in value.split("@")[-1] or " " in value):
            raise ValueError("Enter a valid email address, like name@example.com")
        return value


class RoleProfile(_Base):
    focus: str = ""
    keywords: list[str] = Field(default_factory=list)
    preferred_skill_categories: list[str] = Field(default_factory=list)
    preferred_projects: list[str] = Field(default_factory=list)

    @field_validator("keywords", "preferred_skill_categories", "preferred_projects", mode="before")
    @classmethod
    def clean_lists(cls, value):
        return _clean_list(value)


class Experience(_Base):
    company: str = Field(min_length=1)
    role: str = Field(min_length=1)
    location: str = ""
    dates: str = ""
    type: str = ""
    bullets: list[str] = Field(default_factory=list)

    @field_validator("bullets", mode="before")
    @classmethod
    def clean_lists(cls, value):
        return _clean_list(value)


class Project(_Base):
    title: str = Field(min_length=1)
    tech_stack: str = ""
    highlights: list[str] = Field(default_factory=list)

    @field_validator("highlights", mode="before")
    @classmethod
    def clean_lists(cls, value):
        return _clean_list(value)


class Certification(_Base):
    name: str = Field(min_length=1)
    issuer: str = ""
    year: str = ""


class Education(_Base):
    degree: str = ""
    institution: str = ""
    location: str = ""
    dates: str = ""
    coursework: list[str] = Field(default_factory=list)

    @field_validator("coursework", mode="before")
    @classmethod
    def clean_lists(cls, value):
        return _clean_list(value)


class Resume(_Base):
    personal_info: PersonalInfo = Field(default_factory=PersonalInfo)
    role_profiles: dict[str, RoleProfile] = Field(default_factory=dict)
    standard_answers: dict[str, str] = Field(default_factory=dict)
    core_skills: dict[str, list[str]] = Field(default_factory=dict)
    experience: list[Experience] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    education: Education = Field(default_factory=Education)
    languages: list[str] = Field(default_factory=list)

    @field_validator("role_profiles", "standard_answers", "core_skills", mode="before")
    @classmethod
    def none_to_empty_dict(cls, value):
        return value or {}

    @field_validator("experience", "projects", "certifications", mode="before")
    @classmethod
    def none_to_empty_list(cls, value):
        return value or []

    @field_validator("languages", mode="before")
    @classmethod
    def languages_list(cls, value):
        return _clean_list(value)

    @field_validator("core_skills", mode="after")
    @classmethod
    def skills_lists(cls, value):
        return {name: _clean_list(skills) for name, skills in value.items()}

    @field_validator("education", mode="before")
    @classmethod
    def education_object(cls, value):
        # The CV generator also accepts a list; the editor works on one object, the most recent first.
        if isinstance(value, list):
            return value[0] if value else {}
        return value or {}


def is_empty(resume: Resume) -> bool:
    return not resume.personal_info.full_name.strip() and not resume.experience and not resume.projects


def cross_reference_warnings(resume: Resume, target_roles=None) -> list[str]:
    """Non-blocking problems: links between sections that point at nothing."""
    warnings = []
    categories = set(resume.core_skills)
    titles = {project.title for project in resume.projects}
    for name, profile in resume.role_profiles.items():
        for category in profile.preferred_skill_categories:
            if category not in categories:
                warnings.append(f"Role profile “{name}” uses the skill category “{category}”, which no longer exists.")
        for title in profile.preferred_projects:
            if title not in titles:
                warnings.append(f"Role profile “{name}” lists the project “{title}”, which no longer exists.")
    if target_roles is not None:
        for role in target_roles:
            if role not in resume.role_profiles:
                warnings.append(f"The target role “{role}” has no role profile, so its CVs use the full resume.")
    return warnings
