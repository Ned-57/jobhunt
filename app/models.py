"""Pydantic models.

The profile mirrors the structure of a job-application master document:
contact, core positioning, history, a themed evidence bank, an honest
technology profile, and - importantly - the accuracy boundaries that a
generated CV or letter must never cross.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

from .custard import SmartBulletList, sanitise_deep

# Deliberately loose. Real validation is "can they receive mail", which we
# cannot check here, and a strict regex only ever rejects valid addresses.
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# auth
# --------------------------------------------------------------------------
class Credentials(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=200)

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("That does not look like an email address.")
        return v


class PublicUser(BaseModel):
    id: str
    email: str
    created_at: str


# --------------------------------------------------------------------------
# profile
# --------------------------------------------------------------------------
class Identity(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    portfolio: str = ""
    linkedin: str = ""
    github: str = ""
    links: list[str] = Field(default_factory=list)


class Core(BaseModel):
    summary: str = ""
    positioning: str = ""
    target_roles: SmartBulletList = Field(default_factory=list)
    years: str = ""
    seniority: str = "mid"


class Job(BaseModel):
    company: str = ""
    title: str = ""
    start: str = ""          # YYYY-MM
    end: str = ""            # YYYY-MM, blank when current
    current: bool = False
    location: str = ""
    note: str = ""
    bullets: SmartBulletList = Field(default_factory=list)


class Study(BaseModel):
    school: str = ""
    qualification: str = ""
    field: str = ""
    start: str = ""
    end: str = ""
    note: str = ""


class EvidenceGroup(BaseModel):
    """A themed bundle of defensible claims, not a per-employer bullet list.

    Themes are the right unit for *selection* - a tailored CV pulls the right
    five regardless of who you worked for. But a CV *reads* with bullets under
    the employer, so a theme may optionally name where the work happened.
    Leave it blank and the theme renders as its own section, as before.
    """
    group: str = ""
    employer: str = ""
    items: SmartBulletList = Field(default_factory=list)


class IndependentWork(BaseModel):
    name: str = ""
    url: str = ""
    description: str = ""
    bullets: SmartBulletList = Field(default_factory=list)
    tech: SmartBulletList = Field(default_factory=list)


TechLevel = Literal["production", "project", "training", "exposure", "never"]


class TechArea(BaseModel):
    area: str = ""
    description: str = ""
    level: TechLevel = "project"


class Preferences(BaseModel):
    work_modes: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    salary_min: str = ""
    salary_max: str = ""
    currency: str = "GBP"
    employment: list[str] = Field(default_factory=list)
    company_sizes: list[str] = Field(default_factory=list)
    notice_period: str = ""
    earliest_start: str = ""
    avoid_sectors: list[str] = Field(default_factory=list)
    dealbreakers: SmartBulletList = Field(default_factory=list)


class Positioning(BaseModel):
    role_type: str = ""
    guidance: str = ""


class Style(BaseModel):
    english: str = "British"
    tone: str = ""
    rules: SmartBulletList = Field(default_factory=list)


class DocPrefs(BaseModel):
    font: str = "Calibri"
    accent: str = "#1F3864"
    max_pages: int = 1
    folder: str = ""
    editor: str = ""
    notes: str = ""


class Profile(BaseModel):
    """Everything the app knows about the person applying.

    Text arrives pasted from Word, PDFs and other CVs, so it is normalised on
    the way in - see app.custard.
    """

    identity: Identity = Field(default_factory=Identity)
    core: Core = Field(default_factory=Core)
    employment: list[Job] = Field(default_factory=list)
    education: list[Study] = Field(default_factory=list)
    evidence: list[EvidenceGroup] = Field(default_factory=list)
    independent: list[IndependentWork] = Field(default_factory=list)
    tech: list[TechArea] = Field(default_factory=list)
    prefs: Preferences = Field(default_factory=Preferences)
    positioning: list[Positioning] = Field(default_factory=list)
    boundaries: SmartBulletList = Field(default_factory=list)
    style: Style = Field(default_factory=Style)
    doc_prefs: DocPrefs = Field(default_factory=DocPrefs)
    updated_at: Optional[str] = None
    seen_steps: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _sanitise(cls, data: Any) -> Any:
        return sanitise_deep(data) if isinstance(data, dict) else data
    
    def completeness(self) -> dict[str, Any]:
        """Weighted view of how usable this profile is for prompt building."""
        checks = {
            "Name and contact": bool(self.identity.name and self.identity.email),
            "Where you want to work": bool(self.prefs.locations),
            "What you do": bool(self.core.summary),
            "Target roles": len(self.core.target_roles) > 0,
            "Employment history": len(self.employment) > 0,
            "Evidence bank": sum(len(g.items) for g in self.evidence) >= 5,
            "Technology profile": len(self.tech) >= 3,
            "Preferences": bool(self.prefs.work_modes),
            "Accuracy boundaries": len(self.boundaries) > 0,
        }
        done = sum(1 for v in checks.values() if v)
        return {
            "percent": round(done / len(checks) * 100),
            "done": done,
            "total": len(checks),
            "missing": [k for k, v in checks.items() if not v],
        }


# --------------------------------------------------------------------------
# applications
# --------------------------------------------------------------------------
Stage = Literal["saved", "applied", "interviewing", "closed"]

# Stages describe live states only; how something ended lives in `outcome`.
# Older records used a six-stage set, so they are folded in on read.
STAGE_MIGRATION = {
    # An acknowledgement is an automated email, not a change of state - you are
    # still applied and still waiting.
    "acknowledged": "applied",
    # A screening call is a conversation with a person, so it counts.
    "screening": "interviewing",
    "interview": "interviewing",
    "offer": "closed",
}


class ApplicationEvent(BaseModel):
    at: str = Field(default_factory=now_iso)
    kind: str = "note"
    text: str = ""


class Application(BaseModel):
    id: str = ""
    title: str = ""
    company: str = ""
    location: str = ""
    work_mode: str = ""
    url: str = ""
    source: str = ""
    salary: str = ""
    summary: str = ""
    description: str = ""
    key_requirements: SmartBulletList = Field(default_factory=list)
    why_match: str = ""
    concerns: str = ""
    posted: str = ""

    stage: Stage = "saved"
    outcome: str = ""
    applied_on: str = ""
    next_action: str = ""
    next_action_due: str = ""
    contact_name: str = ""
    contact_email: str = ""
    notes: str = ""
    tags: list[str] = Field(default_factory=list)
    # Which import run this arrived in, so a batch can be reviewed or removed
    # as a unit. Empty for anything added by hand.
    import_batch: str = ""
    match_score: Optional[int] = None
    events: list[ApplicationEvent] = Field(default_factory=list)

    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    @model_validator(mode="before")
    @classmethod
    def _sanitise(cls, data: Any) -> Any:
        return sanitise_deep(data) if isinstance(data, dict) else data

    @model_validator(mode="before")
    @classmethod
    def _migrate_stage(cls, data: Any) -> Any:
        """Fold the old six-stage set into the current one.

        Runs on the raw input because a per-field validator would already have
        rewritten `stage` before it could be inspected.
        """
        if not isinstance(data, dict):
            return data
        old = str(data.get("stage") or "").strip().lower()
        if old not in STAGE_MIGRATION:
            return data

        data = dict(data)
        data["stage"] = STAGE_MIGRATION[old]
        if old == "offer":
            # An offer on the table is not an accepted one, so no outcome is
            # inferred. Record the fact instead of asserting how it ended.
            note = "Was at the Offer stage before the stage set changed."
            existing = str(data.get("notes") or "")
            if note not in existing:
                data["notes"] = (note + "\n\n" + existing).strip()
        return data


class ApplicationList(BaseModel):
    applications: list[Application] = Field(default_factory=list)


# --------------------------------------------------------------------------
# prompt building
# --------------------------------------------------------------------------
PromptKind = Literal["hunt", "assess", "cv", "letter", "interview", "tailor"]


class PromptRequest(BaseModel):
    kind: PromptKind = "hunt"
    brief: str = ""              # free-text steer, e.g. "focus on remote roles, backend"
    advert: str = ""             # pasted job advert for assess/cv/letter/interview
    application_id: str = ""     # or pull the advert from a tracked application
    include_boundaries: bool = True
    max_results: int = 12


class PromptResponse(BaseModel):
    kind: str
    prompt: str
    characters: int
    warnings: list[str] = Field(default_factory=list)


class ImportRequest(BaseModel):
    """Raw text pasted back from an AI tool, to be parsed into applications."""
    text: str
