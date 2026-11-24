"""Tests for the agent loop using a fake LLM – no Ollama required."""

import json
import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db import queries
from app.agent.agent import run_agent, AgentError
from app.config import settings


# ── Fake LLM ──────────────────────────────────────────────────────────────────


class FakeLLM:
    """Returns scripted JSON responses in order.

    If a call receives a message containing 'not valid JSON' (the retry
    prompt), it pops from ``retry_responses`` instead.  When a retry
    response is consumed, the remaining retry_responses are prepended to
    the main responses list so subsequent calls continue naturally.
    """

    def __init__(self, responses: list[str], retry_responses: list[str] | None = None):
        self._responses = list(responses)
        self._retry_responses = list(retry_responses or [])
        self.call_count = 0

    def chat(self, messages: list[dict]) -> str:
        self.call_count += 1
        # Check if this is a retry prompt
        last_user = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
        )
        if "not valid JSON" in last_user and self._retry_responses:
            resp = self._retry_responses.pop(0)
            # Move remaining retry responses to main list so the flow continues
            self._responses = self._retry_responses + self._responses
            self._retry_responses = []
            return resp
        if not self._responses:
            return json.dumps({"tool": "finish", "arguments": {}})
        return self._responses.pop(0)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def db_session():
    """In-memory SQLite session for tests."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def _lower_step_cap(monkeypatch):
    """Allow tests to run with the default step cap."""
    monkeypatch.setattr(settings, "MAX_AGENT_STEPS", 6)


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_path(db_session):
    """Agent calls tools in order: extract -> match -> save -> finish."""
    # Seed a user profile
    queries.upsert_profile(db_session, "Tester", ["python", "docker", "fastapi"])

    responses = [
        # Step 1: extract_posting_fields
        json.dumps(
            {
                "tool": "extract_posting_fields",
                "arguments": {"text": "We are hiring a Python developer at Acme Corp."},
            }
        ),
        # The extract tool internally calls llm.chat – this is the extraction response
        json.dumps(
            {
                "company": "Acme Corp",
                "role_title": "Python Developer",
                "location": "Remote",
                "deadline": "2025-03-01",
                "required_skills": ["Python", "Docker", "AWS"],
            }
        ),
        # Step 2: match_skills
        json.dumps(
            {
                "tool": "match_skills",
                "arguments": {"required_skills": ["Python", "Docker", "AWS"]},
            }
        ),
        # Step 3: save_application
        json.dumps(
            {
                "tool": "save_application",
                "arguments": {
                    "fields": {
                        "company": "Acme Corp",
                        "role_title": "Python Developer",
                        "location": "Remote",
                        "deadline": "2025-03-01",
                        "required_skills": ["Python", "Docker", "AWS"],
                        "matched_skills": ["Python", "Docker"],
                        "missing_skills": ["AWS"],
                        "match_score": 0.6667,
                    }
                },
            }
        ),
        # Step 4: finish
        json.dumps({"tool": "finish", "arguments": {"application_id": 1}}),
    ]

    llm = FakeLLM(responses)
    app_id, steps = await run_agent(
        llm=llm,
        db=db_session,
        posting_text="We are hiring a Python developer at Acme Corp.",
    )

    assert app_id == 1
    # Steps: extract, match, save, finish
    assert len(steps) == 4
    assert steps[0].tool == "extract_posting_fields"
    assert steps[1].tool == "match_skills"
    assert steps[2].tool == "save_application"
    assert steps[3].tool == "finish"


@pytest.mark.asyncio
async def test_step_cap_exceeded(db_session):
    """Agent raises AgentError when it exceeds the step cap without finishing."""
    # Create responses that never finish – just keep extracting
    responses = [
        json.dumps(
            {"tool": "extract_posting_fields", "arguments": {"text": "some posting"}}
        ),
        # extraction LLM response
        json.dumps(
            {
                "company": "X",
                "role_title": "Y",
                "location": "Z",
                "deadline": None,
                "required_skills": [],
            }
        ),
    ] * 10  # More than MAX_AGENT_STEPS

    llm = FakeLLM(responses)
    with pytest.raises(AgentError, match="exceeded maximum steps"):
        await run_agent(llm=llm, db=db_session, posting_text="Some job posting")


@pytest.mark.asyncio
async def test_invalid_json_triggers_retry(db_session):
    """When the LLM returns invalid JSON, the agent retries once."""
    queries.upsert_profile(db_session, "Tester", ["python"])

    responses = [
        # First response: invalid JSON
        "This is not valid JSON at all!",
    ]
    retry_responses = [
        # After retry prompt, return valid tool call
        json.dumps(
            {
                "tool": "extract_posting_fields",
                "arguments": {"text": "Job posting text"},
            }
        ),
    ]

    # Remaining responses that come after the retry flow resumes
    remaining = [
        # extraction LLM sub-call response
        json.dumps(
            {
                "company": "RetryInc",
                "role_title": "Dev",
                "location": "NYC",
                "deadline": None,
                "required_skills": ["Python"],
            }
        ),
        # match
        json.dumps(
            {"tool": "match_skills", "arguments": {"required_skills": ["Python"]}}
        ),
        # save
        json.dumps(
            {
                "tool": "save_application",
                "arguments": {
                    "fields": {
                        "company": "RetryInc",
                        "role_title": "Dev",
                        "location": "NYC",
                        "deadline": None,
                        "required_skills": ["Python"],
                        "matched_skills": ["Python"],
                        "missing_skills": [],
                        "match_score": 1.0,
                    }
                },
            }
        ),
        # finish
        json.dumps({"tool": "finish", "arguments": {"application_id": 1}}),
    ]

    llm = FakeLLM(responses + remaining, retry_responses=retry_responses)
    app_id, steps = await run_agent(
        llm=llm, db=db_session, posting_text="Job posting text"
    )

    assert app_id == 1
    # The retry should have happened (call_count > number of tool steps)
    assert llm.call_count >= 2


@pytest.mark.asyncio
async def test_missing_input_raises(db_session):
    """Agent raises AgentError when neither text nor URL is provided."""
    llm = FakeLLM([])
    with pytest.raises(AgentError, match="posting_text or posting_url"):
        await run_agent(llm=llm, db=db_session)


@pytest.mark.asyncio
async def test_agent_run_persistence_and_order(db_session):
    """Verify that agent steps are recorded in order, persisted, and step count <= MAX_AGENT_STEPS."""
    queries.upsert_profile(db_session, "Tester", ["python", "docker"])

    expected_tool_order = [
        "extract_posting_fields",
        "match_skills",
        "save_application",
        "finish",
    ]

    responses = [
        json.dumps(
            {
                "tool": "extract_posting_fields",
                "arguments": {"text": "Junior Python Dev at Startup"},
            }
        ),
        json.dumps(
            {
                "company": "Startup",
                "role_title": "Junior Python Dev",
                "location": "Remote",
                "deadline": None,
                "required_skills": ["Python", "Docker"],
            }
        ),
        json.dumps(
            {
                "tool": "match_skills",
                "arguments": {"required_skills": ["Python", "Docker"]},
            }
        ),
        json.dumps(
            {
                "tool": "save_application",
                "arguments": {
                    "fields": {
                        "company": "Startup",
                        "role_title": "Junior Python Dev",
                        "location": "Remote",
                        "deadline": None,
                        "required_skills": ["Python", "Docker"],
                        "matched_skills": ["Python", "Docker"],
                        "missing_skills": [],
                        "match_score": 1.0,
                    }
                },
            }
        ),
        json.dumps({"tool": "finish", "arguments": {"application_id": 1}}),
    ]

    llm = FakeLLM(responses)
    app_id, steps = await run_agent(
        llm=llm, db=db_session, posting_text="Junior Python Dev at Startup"
    )

    # Assert step count <= MAX_AGENT_STEPS
    assert len(steps) <= settings.MAX_AGENT_STEPS

    # Assert steps are recorded in exact execution order
    recorded_tools = [s.tool for s in steps]
    assert recorded_tools == expected_tool_order

    # Assert run is persisted in the database
    runs = queries.list_agent_runs(db_session)
    assert len(runs) >= 1
    latest_run = runs[0]
    assert latest_run.application_id == app_id
    assert latest_run.status.value == "success"
    assert len(latest_run.steps) == len(steps)
    assert [s["tool"] for s in latest_run.steps] == expected_tool_order



def test_save_application_ignores_unknown_llm_fields(db_session):
    """Regression: an extra key from the LLM (e.g. 'next_step') must not crash the save."""
    from app.agent.tools import save_application

    app_id = save_application(
        {"company": "Acme", "role_title": "ML Intern", "next_step": "apply", "id": 999},
        db_session,
    )
    saved = queries.get_application(db_session, app_id)
    assert saved.company == "Acme"
    assert saved.role_title == "ML Intern"
    assert saved.id != 999  # the LLM cannot choose the primary key
