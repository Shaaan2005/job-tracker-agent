"""FastAPI route definitions."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.agent.agent import run_agent, AgentError
from app.agent.llm import OllamaLLM, get_llm_client
from app.config import settings
from app.db.database import get_db
from app.db import queries
from app.db.models import ApplicationStatus
from app.schemas import (
    AgentRunResponse,
    ApplicationCreate,
    ApplicationResponse,
    ApplicationStatusUpdate,
    ProfileCreate,
    ProfileResponse,
    StatsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Health ─────────────────────────────────────────────────────────────────────


@router.get("/health")
def health():
    """Liveness probe."""
    return {"status": "ok"}


# ── Profile ────────────────────────────────────────────────────────────────────


@router.post("/profile", response_model=ProfileResponse)
def create_profile(body: ProfileCreate, db: Session = Depends(get_db)):
    """Create or replace the user profile."""
    profile = queries.upsert_profile(db, name=body.name, skills=body.skills)
    return profile


@router.get("/profile", response_model=ProfileResponse)
def get_profile(db: Session = Depends(get_db)):
    """Return the current user profile."""
    profile = queries.get_profile(db)
    if profile is None:
        raise HTTPException(status_code=404, detail="No profile found")
    return profile


# ── Agent Runs ─────────────────────────────────────────────────────────────────


@router.get("/agent-runs", response_model=list[AgentRunResponse])
def get_agent_runs(limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    """List recent agent execution runs with steps taken."""
    return queries.list_agent_runs(db, limit=limit)


# ── LLM Status ─────────────────────────────────────────────────────────────────


@router.get("/llm/status")
def get_llm_status():
    """Return the active LLM backend status and model without exposing secrets."""
    backend = settings.LLM_BACKEND.lower().strip()
    is_ready = False
    model_name = ""
    message = ""

    if backend == "remote":
        model_name = settings.REMOTE_LLM_MODEL
        is_ready = bool(settings.REMOTE_LLM_API_KEY)
        message = (
            f"Remote cloud inference active ({model_name})"
            if is_ready
            else "REMOTE_LLM_API_KEY is not configured. Cloud inference is paused."
        )
    elif backend == "ollama":
        model_name = settings.OLLAMA_MODEL
        is_ready = True
        message = f"Local Ollama active ({model_name})"
    else:
        backend = "disabled"
        model_name = "None"
        message = (
            "LLM inference is disabled. Set LLM_BACKEND=remote with REMOTE_LLM_API_KEY "
            "to enable cloud AI extraction."
        )

    return {
        "backend": backend,
        "model": model_name,
        "is_ready": is_ready,
        "message": message,
    }


# ── Applications ───────────────────────────────────────────────────────────────


@router.post("/applications", response_model=ApplicationResponse)
async def create_application(body: ApplicationCreate, db: Session = Depends(get_db)):
    """Run the agent on a posting and save the application."""
    if settings.LLM_BACKEND == "disabled":
        raise HTTPException(
            status_code=503,
            detail="LLM backend is disabled in this deployment mode. To enable cloud extraction, set LLM_BACKEND=remote and configure REMOTE_LLM_API_KEY in environment variables.",
        )

    if settings.LLM_BACKEND == "remote" and not settings.REMOTE_LLM_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Remote LLM backend is selected, but REMOTE_LLM_API_KEY is missing. Please set REMOTE_LLM_API_KEY in your environment variables.",
        )

    if not body.posting_text and not body.posting_url:
        raise HTTPException(
            status_code=422,
            detail="Provide either posting_text or posting_url",
        )

    try:
        llm = get_llm_client()
    except Exception as exc:
        logger.error("Failed to initialize LLM client: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))

    try:
        app_id, steps = await run_agent(
            llm=llm,
            db=db,
            posting_text=body.posting_text,
            posting_url=body.posting_url,
        )
    except AgentError as exc:
        logger.error("Agent failed: %s", exc)
        err_msg = str(exc)
        if "429" in err_msg or "Too Many Requests" in err_msg:
            raise HTTPException(
                status_code=429,
                detail="Groq API rate limit reached (30 RPM / 8,000 TPM on Free plan). Please wait 30-60 seconds before submitting another posting.",
            )
        raise HTTPException(status_code=500, detail=err_msg)

    app = queries.get_application(db, app_id)
    if app is None:
        raise HTTPException(status_code=500, detail="Application not found after save")
    return app


# NOTE: /applications/stats must be registered BEFORE /applications/{app_id}
# so that "stats" is not captured as an {app_id} path parameter.


@router.get("/applications/stats", response_model=StatsResponse)
def application_stats(db: Session = Depends(get_db)):
    """Return counts per status and counts per ISO week."""
    return queries.get_stats(db)


@router.get("/applications", response_model=list[ApplicationResponse])
def list_applications(
    status: ApplicationStatus | None = Query(None),
    min_match_score: float | None = Query(None),
    company: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """List applications with optional filters."""
    return queries.list_applications(
        db, status=status, min_match_score=min_match_score, company=company
    )


@router.get("/applications/{app_id}", response_model=ApplicationResponse)
def get_application(app_id: int, db: Session = Depends(get_db)):
    """Return a single application by id."""
    app = queries.get_application(db, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


@router.patch("/applications/{app_id}", response_model=ApplicationResponse)
def update_application_status(
    app_id: int,
    body: ApplicationStatusUpdate,
    db: Session = Depends(get_db),
):
    """Update only the status of an application."""
    app = queries.update_application_status(db, app_id, body.status)
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return app
