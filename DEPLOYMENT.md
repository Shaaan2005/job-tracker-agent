# Deployment Guide

This document describes deployment options for **job-tracker-agent**.

> **Note on Live URL**:
> The production endpoint is designated as:
> ```
> https://job-tracker-agent-twrl.onrender.com
> ```
> *(Live Web Service deployed on Render)*

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

---

## Option C: Render Cloud Deployment (Zero-Cost Portfolio Demo)

Render provides free hosting for web services with automatic HTTPS and git push-to-deploy.

### Storage Model & Hosting Limitations

> **IMPORTANT: Free Tier Storage is Ephemeral**
> - **SQLite on Render Free Tier**: Render's free web services run in containers with an **ephemeral filesystem**. The local SQLite database (`job_tracker.db`) will be **reset to empty** whenever the service spins down due to inactivity (after 15 minutes of idle time), restarts, or redeploys.
> - **Suitability for Portfolio Demos**: This ephemeral SQLite setup is ideal for portfolio showcases: it costs $0.00, requires no cloud database configuration, and uses synthetic demo data that visitors can generate and explore fresh on each visit.
> - **Render Free PostgreSQL Limitation**: While Render offers a free managed PostgreSQL add-on, it **expires and is deleted after 30 days**, making it unsuitable for persistent long-term portfolio demos without continuous recreation.

### Long-Term Persistent Storage Alternatives (If Required)
If you require persistent data retention beyond ephemeral demo storage:
1. **Free Serverless PostgreSQL (Recommended Zero-Cost Permanent Storage)**:
   - Use a free serverless PostgreSQL provider such as **Neon** (`neon.tech`) or **Supabase** (`supabase.com`).
   - Neon offers a generous free tier (0.5 GB storage, auto-suspend, no 30-day drop as long as active once every 90 days).
   - Configuration: Set `DATABASE_URL=postgresql://user:password@ep-xyz.neon.tech/dbname?sslmode=require` in Render Environment Variables.
2. **Render Paid Persistent Disk**:
   - Requires upgrading to a Render Paid Web Service plan (Starter plan starts at **$7/month**) + Persistent Disk (**$0.25/GB/month**, minimum 1 GB).
   - Configuration: Attach a persistent disk mounted to `/data` and set `DATABASE_URL=sqlite:////data/job_tracker.db`.

### Instance & Compute Limits
- **RAM**: 512 MB memory ceiling on free web services.
- **Inactivity Sleep**: Free instances sleep after 15 minutes of inactivity; the initial cold-start request after sleep takes ~30–50 seconds to wake up.
- **LLM Mode**: By default, `LLM_BACKEND=disabled` in [`render.yaml`](render.yaml) so the app runs cleanly without an external API key.

### Enabling Zero-Cost Remote LLM Inference in the Cloud
To enable live AI skill extraction on the deployed Render site without crashing the 512 MB RAM limit:
1. **Get a Free API Key**:
   - Recommended provider: **Groq** ([console.groq.com](https://console.groq.com)).
   - **Cost**: $0.00 (Free tier with generous rate limits, no credit card required).
   - Generates an API key (e.g. `gsk_...`) supporting OpenAI-compatible chat completions with `llama-3.1-8b-instant`.
2. **Add Environment Variables in Render**:
   - In Render Dashboard $\rightarrow$ select `job-tracker-agent` $\rightarrow$ **Environment**.
   - Set:
     - `LLM_BACKEND`: `remote`
     - `REMOTE_LLM_URL`: `https://api.groq.com/openai/v1`
     - `REMOTE_LLM_MODEL`: `llama-3.1-8b-instant`
     - `REMOTE_LLM_API_KEY`: `<your-groq-api-key>`
   - Click **Save Changes**. Render will automatically redeploy and live AI extraction will be active!

---

### Step-by-Step Instructions to Connect Repository to Render

#### 1. Push Local Git Repository to GitHub
*(Perform these commands when you are ready to publish)*
```bash
# From the project directory:
cd job-tracker-agent

# Set your GitHub remote repository URL:
git remote add origin https://github.com/<your-github-username>/job-tracker-agent.git

# Set main branch and push:
git branch -M main
git push -u origin main
```

#### 2. Connect Repository on Render
1. Log in to [dashboard.render.com](https://dashboard.render.com).
2. Click **New +** (top right) $\rightarrow$ **Blueprint**.
3. Connect your GitHub account and select your `job-tracker-agent` repository.
4. Render automatically detects [`render.yaml`](render.yaml) and displays the blueprint configuration:
   - **Service Name**: `job-tracker-agent`
   - **Runtime**: `Python 3`
   - **Plan**: `Free` ($0.00/mo)
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Environment Variables**: `LLM_BACKEND=disabled`, `DATABASE_URL=sqlite:///./job_tracker.db`
5. Click **Apply** to trigger the initial deployment.

#### 3. Verify the Live Demo
- Render assigns a public URL: `https://job-tracker-agent-<unique-id>.onrender.com`.
- Verify the health check:
  ```bash
  curl https://job-tracker-agent-<unique-id>.onrender.com/health
  # Expected: {"status":"ok"}
  ```
- Open the live URL in your browser: the dashboard will load with candidate profile setup, demo posting presets, application tracking, and stats.

