"""SQLAlchemy ORM models for Application, UserProfile, and AgentRun."""

import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class ApplicationStatus(str, enum.Enum):
    """Allowed statuses for a job application."""

    saved = "saved"
    applied = "applied"
    interview = "interview"
    offer = "offer"
    rejected = "rejected"


class AgentRunStatus(str, enum.Enum):
    """Terminal status of an agent run."""

    success = "success"
    error = "error"
    step_cap = "step_cap"


class Application(Base):
    """A tracked job application."""

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company: Mapped[str] = mapped_column(String(256), nullable=False)
    role_title: Mapped[str] = mapped_column(String(256), nullable=False)
    location: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    deadline: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus), nullable=False, default=ApplicationStatus.saved
    )
    source_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    required_skills: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    matched_skills: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    missing_skills: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    match_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class UserProfile(Base):
    """Single-row table holding the user's name and skill list."""

    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False, default="User")
    skills: Mapped[list] = mapped_column(JSON, nullable=False, default=list)


class AgentRun(Base):
    """Persisted record of a single agent execution and its steps."""

    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[AgentRunStatus] = mapped_column(
        Enum(AgentRunStatus), nullable=False, default=AgentRunStatus.success
    )
    steps: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    json_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
