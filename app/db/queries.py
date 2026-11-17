"""Database query helpers for applications, profiles, and agent runs."""

from datetime import datetime, timezone
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import Application, ApplicationStatus, UserProfile, AgentRun, AgentRunStatus


def get_profile(db: Session) -> UserProfile | None:
    """Return the single user profile row, or None."""
    return db.query(UserProfile).first()


def upsert_profile(db: Session, name: str, skills: list[str]) -> UserProfile:
    """Create or replace the user profile (single-row table)."""
    profile = db.query(UserProfile).first()
    if profile is None:
        profile = UserProfile(name=name, skills=skills)
        db.add(profile)
    else:
        profile.name = name
        profile.skills = skills
    db.commit()
    db.refresh(profile)
    return profile


def create_application(db: Session, **kwargs) -> Application:
    """Insert a new application and return it."""
    app = Application(**kwargs)
    db.add(app)
    db.commit()
    db.refresh(app)
    return app


def list_applications(
    db: Session,
    status: ApplicationStatus | None = None,
    min_match_score: float | None = None,
    company: str | None = None,
) -> list[Application]:
    """List applications with optional filters."""
    q = db.query(Application)
    if status is not None:
        q = q.filter(Application.status == status)
    if min_match_score is not None:
        q = q.filter(Application.match_score >= min_match_score)
    if company is not None:
        q = q.filter(Application.company.ilike(f"%{company}%"))
    return q.order_by(Application.created_at.desc()).all()


def get_application(db: Session, app_id: int) -> Application | None:
    """Return a single application by id."""
    return db.query(Application).filter(Application.id == app_id).first()


def update_application_status(
    db: Session, app_id: int, status: ApplicationStatus
) -> Application | None:
    """Update only the status of an application."""
    app = get_application(db, app_id)
    if app is None:
        return None
    app.status = status
    db.commit()
    db.refresh(app)
    return app


def get_stats(db: Session) -> dict:
    """Return count per status and count created per ISO week."""
    status_rows = (
        db.query(Application.status, func.count(Application.id))
        .group_by(Application.status)
        .all()
    )
    status_counts = {row[0].value: row[1] for row in status_rows}

    week_rows = (
        db.query(
            func.strftime("%Y-W%W", Application.created_at).label("week"),
            func.count(Application.id),
        )
        .group_by("week")
        .order_by("week")
        .all()
    )
    weekly_counts = [{"week": row[0], "count": row[1]} for row in week_rows]

    return {"status_counts": status_counts, "weekly_counts": weekly_counts}


def create_agent_run(db: Session) -> AgentRun:
    """Create a new agent run record."""
    run = AgentRun(
        started_at=datetime.now(timezone.utc),
        status=AgentRunStatus.success,
        steps=[],
        json_retries=0,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def finish_agent_run(
    db: Session,
    run_id: int,
    status: AgentRunStatus,
    steps: list[dict],
    application_id: int | None = None,
    json_retries: int = 0,
) -> AgentRun | None:
    """Finalize an agent run record."""
    run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
    if not run:
        return None
    run.finished_at = datetime.now(timezone.utc)
    run.status = status
    run.steps = steps
    run.application_id = application_id
    run.json_retries = json_retries
    db.commit()
    db.refresh(run)
    return run


def list_agent_runs(db: Session, limit: int = 50) -> list[AgentRun]:
    """List recent agent runs ordered by started_at descending."""
    return db.query(AgentRun).order_by(AgentRun.started_at.desc()).limit(limit).all()
