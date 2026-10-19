from pydantic import BaseModel, ConfigDict, Field, field_validator


def _clean(values):
    seen, result = set(), []
    for value in values or []:
        text = str(value).strip()
        if text and text.lower() not in seen:
            seen.add(text.lower())
            result.append(text)
    return result


class Sources(BaseModel):
    adzuna: bool = True
    arbeitnow: bool = True
    gmail: bool = True


class AdzunaSettings(BaseModel):
    country: str = Field("be", min_length=2, max_length=2)
    location: str = "Belgium"
    results_per_page: int = Field(50, ge=1, le=50)


class GmailSettings(BaseModel):
    senders: list[str] = Field(default_factory=list)
    lookback_days: int = Field(2, ge=1, le=30)
    max_results: int = Field(100, ge=1, le=500)

    @field_validator("senders", mode="before")
    @classmethod
    def clean_senders(cls, value):
        senders = []
        for sender in _clean(value):
            sender = sender.lower().removeprefix("from:").lstrip("@")
            if " " in sender or not sender:
                raise ValueError(f"“{sender}” is not a sender domain or address")
            senders.append(sender)
        return senders


class CoverLetter(BaseModel):
    opening: str = ""
    evidence: str = ""
    fit: str = ""
    closing: str = ""


class Alerts(BaseModel):
    smtp_enabled: bool = False


class SearchSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_roles: dict[str, list[str]]
    extra_keywords: list[str] = Field(default_factory=list)
    search_queries: dict[str, list[str]] = Field(default_factory=dict)
    entry_level_keywords: list[str] = Field(default_factory=list)
    exclude_title_keywords: list[str] = Field(default_factory=list)
    allowed_locations: list[str] = Field(min_length=1)
    blocked_locations: list[str] = Field(default_factory=list)
    trusted_alert_sources: list[str] = Field(default_factory=list)
    time_window_hours: int = Field(48, ge=1, le=24 * 60)
    sources: Sources = Field(default_factory=Sources)
    adzuna: AdzunaSettings = Field(default_factory=AdzunaSettings)
    gmail: GmailSettings = Field(default_factory=GmailSettings)
    cover_letters: dict[str, CoverLetter] = Field(default_factory=dict)
    alerts: Alerts = Field(default_factory=Alerts)

    @field_validator("target_roles", "search_queries", mode="before")
    @classmethod
    def clean_maps(cls, value):
        cleaned = {}
        for name, keywords in (value or {}).items():
            name = str(name).strip()
            if not name:
                raise ValueError("Every role needs a name")
            cleaned[name] = _clean(keywords)
        return cleaned

    @field_validator("target_roles")
    @classmethod
    def at_least_one_role(cls, value):
        if not value:
            raise ValueError("Add at least one target role")
        for name, keywords in value.items():
            if not keywords:
                raise ValueError(f"The role “{name}” needs at least one keyword")
        return value

    @field_validator(
        "extra_keywords", "entry_level_keywords", "exclude_title_keywords", "blocked_locations",
        "trusted_alert_sources", mode="before",
    )
    @classmethod
    def clean_lists(cls, value):
        return _clean(value)

    @field_validator("allowed_locations", mode="before")
    @classmethod
    def clean_locations(cls, value):
        return [location.lower() for location in _clean(value)]

    @field_validator("blocked_locations", mode="after")
    @classmethod
    def lower_blocked(cls, value):
        return [location.lower() for location in value]


def settings_warnings(settings: dict, resume_role_profiles=None) -> list[str]:
    warnings = []
    roles = set(settings.get("target_roles", {}))
    for role in settings.get("search_queries", {}):
        if role not in roles:
            warnings.append(f"Search queries are set for “{role}”, which is not a target role.")
    for role in roles:
        if not settings.get("search_queries", {}).get(role):
            warnings.append(f"“{role}” has no Adzuna search queries, so Adzuna will not search for it.")
    if resume_role_profiles is not None:
        for role in roles - set(resume_role_profiles):
            warnings.append(f"“{role}” has no role profile in your resume yet. Add one under Profile → Role profiles.")
    return warnings
