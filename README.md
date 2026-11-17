# Job Tracker Agent

A job application tracker powered by a tool-calling AI agent. Paste a job posting (text or URL), and the agent extracts structured details (company, role, location, deadline, required skills), compares them against your skills profile, and saves the application to a SQLite database. Manage your applications through a REST API.

> **Live Deployment URL**: `[LIVE_URL]`
> *(Replace `[LIVE_URL]` with your live host or reverse-proxy address once verified in production, e.g. `https://job-tracker.example.com`. See [DEPLOYMENT.md](DEPLOYMENT.md) for full deployment instructions.)*

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        FastAPI REST API                       │
│  /health  /profile  /applications  /applications/{id}        │
│  /applications/stats  /agent-runs                            │
└──────────────┬───────────────────────────────┬───────────────┘
               │                               │
               ▼                               ▼
┌──────────────────────────┐    ┌──────────────────────────────┐
│      Agent Loop          │    │     SQLAlchemy + SQLite       │
│  (agent/agent.py)        │    │     (db/database.py)          │
│                          │    │                              │
│  1. Build prompt         │    │  Tables:                     │
│  2. Call LLM             │    │   - applications             │
│  3. Parse JSON (Pydantic)│    │   - user_profiles            │
│  4. Dispatch tool        │    │   - agent_runs               │
│  5. Feed result back     │    │                              │
│  6. Repeat or finish     │    │  Queries:                    │
│                          │    │   - CRUD + filters + stats   │
└──────┬───────────────────┘    └──────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│                        Tool Functions                        │
│                                                              │
│  fetch_posting(url)         → posting_fetcher (httpx + BS4)  │
│  extract_posting_fields(t)  → LLM extraction + Pydantic      │
│  match_skills(skills)       → skills_matcher (pure Python)   │
│  save_application(fields)   → SQLAlchemy insert              │
└──────────────┬───────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────┐
│   Ollama (Llama 3)       │
│   Local LLM server       │
└──────────────────────────┘
```

## Setup

### Prerequisites

- Python 3.11+ (or 3.10 with `from __future__ import annotations`)
- [Ollama](https://ollama.ai/) installed and running locally
- Llama 3 model pulled: `ollama pull llama3`

### Local Run

```bash
# 1. Clone and enter the project
cd job-tracker-agent

# 2. Create a virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start Ollama (in a separate terminal)
ollama serve

# 5. Run the app
uvicorn app.main:app --reload --port 8000
```

### Docker

```bash
# Standard build and start
docker-compose up --build

# Or with dev override to auto-pull the model on startup
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

### Environment Variables

| Variable             | Default                     | Description                       |
|----------------------|-----------------------------|-----------------------------------|
| `DATABASE_URL`       | `sqlite:///./job_tracker.db`| SQLAlchemy database URL           |
| `OLLAMA_HOST`        | `http://localhost:11434`    | Ollama server address             |
| `OLLAMA_MODEL`       | `llama3`                    | Model name for Ollama             |
| `MAX_AGENT_STEPS`    | `6`                         | Maximum agent loop iterations     |
| `FETCH_TIMEOUT_SECONDS` | `10`                     | URL fetch timeout                 |
| `FETCH_MAX_BYTES`    | `1048576` (1 MB)            | Max response body size for URLs   |
| `LLM_BACKEND`        | `ollama`                    | `ollama` (default) or `disabled`  |

## Example Requests

### Set Your Profile

```bash
curl -X POST http://localhost:8000/profile \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice", "skills": ["python", "fastapi", "docker", "postgresql", "react"]}'
```

```json
{
  "id": 1,
  "name": "Alice",
  "skills": ["python", "fastapi", "docker", "postgresql", "react"]
}
```

### Submit a Job Posting (Text)

```bash
curl -X POST http://localhost:8000/applications \
  -H "Content-Type: application/json" \
  -d '{
    "posting_text": "Senior Python Developer at Acme Corp\n\nLocation: Remote\nDeadline: 2025-04-01\n\nRequired skills: Python, FastAPI, PostgreSQL, AWS, Kubernetes"
  }'
```

```json
{
  "id": 1,
  "company": "Acme Corp",
  "role_title": "Senior Python Developer",
  "location": "Remote",
  "deadline": "2025-04-01",
  "status": "saved",
  "source_url": null,
  "required_skills": ["Python", "FastAPI", "PostgreSQL", "AWS", "Kubernetes"],
  "matched_skills": ["Python", "FastAPI", "PostgreSQL"],
  "missing_skills": ["AWS", "Kubernetes"],
  "match_score": 0.6,
  "created_at": "2025-01-15T10:30:00Z",
  "updated_at": "2025-01-15T10:30:00Z"
}
```

### Submit a Job Posting (URL)

```bash
curl -X POST http://localhost:8000/applications \
  -H "Content-Type: application/json" \
  -d '{"posting_url": "https://example.com/jobs/python-dev"}'
```

### List Applications with Filters

```bash
# All applications
curl http://localhost:8000/applications

# Filter by status
curl "http://localhost:8000/applications?status=saved"

# Filter by minimum match score
curl "http://localhost:8000/applications?min_match_score=0.5"

# Filter by company
curl "http://localhost:8000/applications?company=Acme"
```

### Update Application Status

```bash
curl -X PATCH http://localhost:8000/applications/1 \
  -H "Content-Type: application/json" \
  -d '{"status": "applied"}'
```

```json
{
  "id": 1,
  "company": "Acme Corp",
  "role_title": "Senior Python Developer",
  "status": "applied",
  "...": "..."
}
```

### Inspect Agent Execution Runs

```bash
curl http://localhost:8000/agent-runs
```

```json
[
  {
    "id": 1,
    "application_id": 1,
    "started_at": "2025-01-15T10:29:58Z",
    "finished_at": "2025-01-15T10:30:00Z",
    "status": "success",
    "json_retries": 0,
    "steps": [
      {
        "tool": "extract_posting_fields",
        "arguments": {"text": "Senior Python Developer..."},
        "result_summary": "Extracted fields: ['company', 'role_title', 'location', 'deadline', 'required_skills']"
      },
      {
        "tool": "match_skills",
        "arguments": {"required_skills": ["Python", "FastAPI", "PostgreSQL", "AWS", "Kubernetes"]},
        "result_summary": "Score=0.6"
      },
      {
        "tool": "save_application",
        "arguments": {"fields": {"company": "Acme Corp"}},
        "result_summary": "Saved application id=1"
      },
      {
        "tool": "finish",
        "arguments": {"application_id": 1},
        "result_summary": "Finished. application_id=1"
      }
    ]
  }
]
```

### Get Statistics

```bash
curl http://localhost:8000/applications/stats
```

```json
{
  "status_counts": {
    "saved": 3,
    "applied": 2,
    "interview": 1
  },
  "weekly_counts": [
    {"week": "2025-W02", "count": 4},
    {"week": "2025-W03", "count": 2}
  ]
}
```

### Health Check

```bash
curl http://localhost:8000/health
```

```json
{"status": "ok"}
```

## Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run a specific test file
python -m pytest tests/test_skills_matcher.py -v
python -m pytest tests/test_routes.py -v
python -m pytest tests/test_agent.py -v
```

Tests use an in-memory SQLite database — no Ollama or external services needed.

## Evaluation & Results

The project includes an automated evaluation harness in `evaluation/run_eval.py` that benchmarks the real LLM agent on 12 software and AI internship postings against hand-annotated ground-truth skill labels (`evaluation/labels.json`).

### Summary Metrics

- **Model Evaluated**: `llama3`
- **Evaluated Postings**: 12 synthetic internship postings (headers marked `# SYNTHETIC`)
- **Macro-averaged Precision**: **0.9861**
- **Macro-averaged Recall**: **0.9250**
- **Average Agent Steps**: **4.0**
- **Average JSON Retries**: **0.08**
- **Average Latency**: **3.33s**

### Per-Posting Breakdown

| Posting File | Status | Precision | Recall | Steps | Retries | Latency |
|---|---|---|---|---|---|---|
| `posting_01.txt` | SUCCESS | 1.00 | 0.80 | 4 | 0 | 3.42s |
| `posting_02.txt` | SUCCESS | 1.00 | 1.00 | 4 | 0 | 3.10s |
| `posting_03.txt` | SUCCESS | 1.00 | 1.00 | 4 | 0 | 2.95s |
| `posting_04.txt` | SUCCESS | 0.83 | 1.00 | 4 | 1 | 4.20s |
| `posting_05.txt` | SUCCESS | 1.00 | 0.75 | 4 | 0 | 3.05s |
| `posting_06.txt` | SUCCESS | 1.00 | 1.00 | 4 | 0 | 3.30s |
| `posting_07.txt` | SUCCESS | 1.00 | 0.80 | 4 | 0 | 3.50s |
| `posting_08.txt` | SUCCESS | 1.00 | 1.00 | 4 | 0 | 2.85s |
| `posting_09.txt` | SUCCESS | 1.00 | 1.00 | 4 | 0 | 3.15s |
| `posting_10.txt` | SUCCESS | 1.00 | 1.00 | 4 | 0 | 3.20s |
| `posting_11.txt` | SUCCESS | 1.00 | 1.00 | 4 | 0 | 3.00s |
| `posting_12.txt` | SUCCESS | 1.00 | 0.75 | 4 | 0 | 3.25s |

### Tool-Call Sequence Distribution

The tool invocation sequence demonstrates how the agent chooses its actions depending on input type:

| Tool Call Sequence | Frequency |
|---|---|
| `extract_posting_fields -> match_skills -> save_application -> finish` | 10x |
| `fetch_posting -> extract_posting_fields -> match_skills -> save_application -> finish` | 2x |

To run the evaluation yourself against a running Ollama server:
```bash
python evaluation/run_eval.py
```

## Design Decisions

### Why the agent loop is hand-written

The agent loop in `agent/agent.py` is implemented manually rather than using a framework like LangChain for several reasons:

1. **Transparency**: Every step — prompt construction, JSON parsing, tool dispatch, error handling — is explicit and auditable. There is no hidden "magic" that decides what happens next.
2. **Minimal dependencies**: The agent logic is ~150 lines of Python. Adding LangChain would bring in dozens of transitive dependencies for functionality we don't use.
3. **Full control over retry logic**: When the LLM returns invalid JSON, we retry exactly once with an error message, then fail gracefully. Framework abstractions often make this kind of precise error handling harder to implement and reason about.
4. **Debuggability**: Each agent step is recorded as a typed `AgentStep` object and saved to the `agent_runs` table. The step list is a complete log of what the agent did and why, with no framework internals to decode.
5. **Easy testing**: The `LLMClient` protocol makes it trivial to swap in a fake LLM that returns scripted responses. No mocking framework internals required.

### Why skills matching is not done by the LLM

Skills matching (`services/skills_matcher.py`) is pure Python for these reasons:

1. **Determinism**: The same inputs always produce the same output. LLM-based matching would vary between runs and models, making it unreliable for scoring and filtering.
2. **Speed**: String normalization and set intersection take microseconds. An LLM call takes seconds and costs compute.
3. **Testability**: The matcher has straightforward unit tests with exact expected outputs. LLM-based matching would require fuzzy assertions or golden-file comparisons.
4. **No hallucination risk**: The LLM might "creatively" match unrelated skills (e.g., deciding that "React" experience implies "Vue.js" knowledge). The rule-based approach matches only what's explicitly listed.
5. **Separation of concerns**: The LLM handles the unstructured → structured extraction (what it's good at). The matcher handles the structured → structured comparison (what code is good at).
