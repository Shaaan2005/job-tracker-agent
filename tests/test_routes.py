"""Tests for API routes using a stubbed agent."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.db import queries
from app.db.models import ApplicationStatus
from app.main import app
from app.schemas import AgentStep


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def db_session():
    """In-memory SQLite session for route tests.

    Uses StaticPool so that all connections share the same in-memory database
    (required because TestClient runs handlers in a background thread).
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()
    yield session
    session.close()


@pytest.fixture()
def client(db_session):
    """TestClient wired to the in-memory database."""

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── Health ─────────────────────────────────────────────────────────────────────


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ── Profile ────────────────────────────────────────────────────────────────────


def test_create_and_get_profile(client):
    resp = client.post(
        "/profile", json={"name": "Alice", "skills": ["python", "docker"]}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Alice"
    assert data["skills"] == ["python", "docker"]

    resp = client.get("/profile")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Alice"


def test_get_profile_not_found(client):
    resp = client.get("/profile")
    assert resp.status_code == 404


def test_profile_replace(client):
    client.post("/profile", json={"name": "V1", "skills": ["a"]})
    client.post("/profile", json={"name": "V2", "skills": ["b", "c"]})
    resp = client.get("/profile")
    assert resp.json()["name"] == "V2"
    assert resp.json()["skills"] == ["b", "c"]


# ── Applications ───────────────────────────────────────────────────────────────


def _seed_application(db_session, **overrides):
    """Helper to insert an application directly into the database."""
    defaults = dict(
        company="TestCo",
        role_title="Engineer",
        location="Remote",
        status=ApplicationStatus.saved,
        source_text="raw posting",
        required_skills=["python"],
        matched_skills=["python"],
        missing_skills=[],
        match_score=1.0,
    )
    defaults.update(overrides)
    return queries.create_application(db_session, **defaults)


def test_create_application_with_stubbed_agent(client, db_session):
    """POST /applications runs the agent (stubbed) and returns the result."""
    # Seed a profile first
    client.post("/profile", json={"name": "Alice", "skills": ["python"]})

    # Pre-create an application so the agent stub can "find" it
    seeded = _seed_application(db_session)

    async def fake_run_agent(llm, db, posting_text=None, posting_url=None):
        return seeded.id, [AgentStep(tool="finish", result_summary="ok")]

    with patch("app.api.routes.run_agent", side_effect=fake_run_agent):
        resp = client.post(
            "/applications", json={"posting_text": "Test posting text"}
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["company"] == "TestCo"


def test_create_application_missing_input(client):
    resp = client.post("/applications", json={})
    assert resp.status_code == 422


def test_list_applications(client, db_session):
    _seed_application(db_session, company="Alpha", match_score=0.8)
    _seed_application(db_session, company="Beta", match_score=0.4)

    resp = client.get("/applications")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_list_filter_by_company(client, db_session):
    _seed_application(db_session, company="Alpha")
    _seed_application(db_session, company="Beta")

    resp = client.get("/applications", params={"company": "Alpha"})
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["company"] == "Alpha"


def test_list_filter_by_min_score(client, db_session):
    _seed_application(db_session, company="High", match_score=0.9)
    _seed_application(db_session, company="Low", match_score=0.2)

    resp = client.get("/applications", params={"min_match_score": 0.5})
    items = resp.json()
    assert len(items) == 1
    assert items[0]["company"] == "High"


def test_list_filter_by_status(client, db_session):
    _seed_application(db_session, status=ApplicationStatus.saved)
    _seed_application(db_session, status=ApplicationStatus.applied)

    resp = client.get("/applications", params={"status": "applied"})
    items = resp.json()
    assert len(items) == 1
    assert items[0]["status"] == "applied"


def test_get_application(client, db_session):
    seeded = _seed_application(db_session)
    resp = client.get(f"/applications/{seeded.id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == seeded.id


def test_get_application_not_found(client):
    resp = client.get("/applications/999")
    assert resp.status_code == 404


def test_patch_application_status(client, db_session):
    seeded = _seed_application(db_session)
    resp = client.patch(
        f"/applications/{seeded.id}", json={"status": "interview"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "interview"


def test_patch_application_not_found(client):
    resp = client.patch("/applications/999", json={"status": "applied"})
    assert resp.status_code == 404


def test_stats(client, db_session):
    _seed_application(db_session, status=ApplicationStatus.saved)
    _seed_application(db_session, status=ApplicationStatus.saved)
    _seed_application(db_session, status=ApplicationStatus.applied)

    resp = client.get("/applications/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status_counts"]["saved"] == 2
    assert data["status_counts"]["applied"] == 1
    assert len(data["weekly_counts"]) >= 1


def test_agent_runs_endpoint(client, db_session):
    """GET /agent-runs returns recorded agent runs."""
    run = queries.create_agent_run(db_session)
    queries.finish_agent_run(
        db_session,
        run_id=run.id,
        status=queries.AgentRunStatus.success,
        steps=[{"tool": "fetch_posting", "result_summary": "ok"}],
        application_id=1,
    )

    resp = client.get("/agent-runs")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 1
    assert items[0]["id"] == run.id
    assert items[0]["steps"][0]["tool"] == "fetch_posting"


def test_llm_backend_disabled(client, monkeypatch):
    """When LLM_BACKEND=disabled, POST /applications returns 503 while others work."""
    from app.config import settings
    monkeypatch.setattr(settings, "LLM_BACKEND", "disabled")

    # POST /applications returns 503
    resp = client.post("/applications", json={"posting_text": "Software Engineer"})
    assert resp.status_code == 503
    assert "disabled" in resp.json()["detail"].lower()

    # Other endpoints still work
    health_resp = client.get("/health")
    assert health_resp.status_code == 200

    profile_resp = client.post("/profile", json={"name": "Bob", "skills": ["python"]})
    assert profile_resp.status_code == 200


def test_llm_status_endpoint(client):
    """GET /llm/status returns backend mode and readiness."""
    resp = client.get("/llm/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "backend" in data
    assert "model" in data
    assert "is_ready" in data


def test_remote_llm_missing_api_key(client, monkeypatch):
    """When LLM_BACKEND=remote and REMOTE_LLM_API_KEY is unset, POST /applications returns 503."""
    from app.config import settings
    monkeypatch.setattr(settings, "LLM_BACKEND", "remote")
    monkeypatch.setattr(settings, "REMOTE_LLM_API_KEY", "")

    resp = client.post("/applications", json={"posting_text": "Software Engineer"})
    assert resp.status_code == 503
    assert "missing" in resp.json()["detail"].lower() or "not set" in resp.json()["detail"].lower()


