# Deployment Guide

This document describes deployment options for **job-tracker-agent**.

> **Note on Live URL**:
> The production endpoint is designated as:
> ```
> [LIVE_URL]
> ```
> *(Replace `[LIVE_URL]` with your domain name or cloud public IP after deploying, e.g., `https://jobs.example.com` or `http://203.0.113.10:8000`.)*

---

## Option A: Full Deployment (App + Local Ollama)

This configuration runs both the FastAPI application and the local Ollama LLM container.

### System Requirements
- **RAM**: Minimum 8 GB (16 GB recommended for smooth Llama 3 inference).
- **CPU**: 4+ vCPUs recommended (or an NVIDIA GPU with nvidia-container-toolkit).
- **Disk**: 15+ GB free space (Docker images + ~4.7 GB Llama 3 weights + SQLite storage).
- **OS**: Linux (Ubuntu 22.04+ recommended), macOS, or Windows with WSL2.

### Step-by-Step Setup

1. **Clone the repository**:
   ```bash
   git clone <repo-url> job-tracker-agent
   cd job-tracker-agent
   ```

2. **Configure environment variables (optional)**:
   You can customize settings in your environment or via a `.env` file:
   ```env
   DATABASE_URL=sqlite:////data/job_tracker.db
   OLLAMA_HOST=http://ollama:11434
   OLLAMA_MODEL=llama3
   MAX_AGENT_STEPS=6
   LLM_BACKEND=ollama
   ```

3. **Start the containers with docker-compose**:
   ```bash
   # Standard start
   docker compose up -d --build
   ```

4. **Pull the Llama 3 model inside Ollama**:
   ```bash
   docker compose exec ollama ollama pull llama3
   ```
   *Alternative:* Use the dev compose file to pull the model automatically:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
   ```

5. **Verify deployment**:
   ```bash
   curl http://localhost:8000/health
   # Expected: {"status":"ok"}
   ```

---

## Option B: Limited Deployment (App Only, LLM Disabled)

For lightweight environments (e.g., small 512 MB – 1 GB VPS, serverless containers, or when local LLM compute is unavailable), you can deploy the app with `LLM_BACKEND=disabled`.

In this mode:
- All database CRUD operations, user profile endpoints, statistics, filtering, and manual status updates work normally.
- `POST /applications` returns `HTTP 503 Service Unavailable` with a descriptive error message explaining that the LLM extraction agent is disabled.

### Setup

1. **Run with Docker**:
   ```bash
   docker build -t job-tracker-agent .
   docker run -d \
     -p 8000:8000 \
     -e LLM_BACKEND=disabled \
     -v job_tracker_data:/data \
     -e DATABASE_URL=sqlite:////data/job_tracker.db \
     job-tracker-agent
   ```

2. **Run locally without Docker**:
   ```bash
   export LLM_BACKEND=disabled
   # Windows PowerShell: $env:LLM_BACKEND="disabled"
   uvicorn app.main:app --port 8000
   ```

3. **Verify endpoints**:
   ```bash
   # 1. Health check works:
   curl http://localhost:8000/health
   # {"status":"ok"}

   # 2. Profile creation works:
   curl -X POST http://localhost:8000/profile \
     -H "Content-Type: application/json" \
     -d '{"name": "Dev", "skills": ["python", "fastapi"]}'

   # 3. Application creation returns 503:
   curl -X POST http://localhost:8000/applications \
     -H "Content-Type: application/json" \
     -d '{"posting_text": "Python Developer needed"}'
   # {"detail": "LLM backend is disabled in this deployment mode."}
   ```
