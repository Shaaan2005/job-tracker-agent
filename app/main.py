"""FastAPI application entry point."""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.api.routes import router
from app.db.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_HTML = STATIC_DIR / "index.html"

app = FastAPI(
    title="Job Tracker Agent",
    version="1.0.0",
    description="Track job applications with an AI agent that extracts posting details.",
)

app.include_router(router)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def get_index():
    """Serve the interactive web interface."""
    if INDEX_HTML.exists():
        with open(INDEX_HTML, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Job Tracker Agent</h1><p>Web UI not found.</p>"


@app.on_event("startup")
def on_startup():
    """Create database tables on first run."""
    init_db()
