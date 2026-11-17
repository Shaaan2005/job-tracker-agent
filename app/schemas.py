"""Pydantic v2 request / response / extraction schemas."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────────────────


class ApplicationStatusEnum(str, Enum):
    saved = "saved"
    applied = "applied"
    interview = "interview"
    offer = "offer"
    rejected = "rejected"


class AgentRunStatusEnum(str, Enum):
    success = "success"
    error = "error"
    step_cap = "step_cap"


# ── Profile ────────────────────────────────────────────────────────────────────


class ProfileCreate(BaseModel):
    name: str = "User"
    skills: list[str]


class ProfileResponse(BaseModel):
    id: int
    name: str
    skills: list[str]

    model_config = {"from_attributes": True}


# ── Application ────────────────────────────────────────────────────────────────


class ApplicationCreate(BaseModel):
    """Either posting_text or posting_url must be provided."""

    posting_text: str | None = None
    posting_url: str | None = None


class ApplicationResponse(BaseModel):
    id: int
    company: str
    role_title: str
    location: str
    deadline: str | None
    status: ApplicationStatusEnum
    source_url: str | None
    required_skills: list[str]
    matched_skills: list[str]
    missing_skills: list[str]
    match_score: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ApplicationStatusUpdate(BaseModel):
    status: ApplicationStatusEnum


class StatsResponse(BaseModel):
    status_counts: dict[str, int]
    weekly_counts: list[dict]


# ── LLM extraction schema ─────────────────────────────────────────────────────


class ExtractedPostingFields(BaseModel):
    """Fields the LLM must extract from a job posting."""

    company: str
    role_title: str
    location: str = ""
    deadline: str | None = None
    required_skills: list[str] = Field(default_factory=list)


# ── Agent protocol ─────────────────────────────────────────────────────


class ToolCall(BaseModel):
    """Shape the LLM must return for each step."""

    tool: str
    arguments: dict = Field(default_factory=dict)


class AgentStep(BaseModel):
    """Record of a single agent step for logging."""

    tool: str
    arguments: dict = Field(default_factory=dict)
    result_summary: str = ""


class SkillsMatchResult(BaseModel):
    """Result of the skills matcher."""

    matched: list[str]
    missing: list[str]
    score: float


# ── Agent Run Log ──────────────────────────────────────────────────────────────


class AgentRunResponse(BaseModel):
    id: int
    application_id: int | None
    started_at: datetime
    finished_at: datetime | None
    status: AgentRunStatusEnum
    steps: list[dict]
    json_retries: int

    model_config = {"from_attributes": True}
