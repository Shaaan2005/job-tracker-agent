"""Application settings loaded from environment variables."""

import os


class Settings:
    """Central configuration loaded from environment variables with defaults."""

    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./job_tracker.db")
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3")
    MAX_AGENT_STEPS: int = int(os.getenv("MAX_AGENT_STEPS", "6"))
    FETCH_TIMEOUT_SECONDS: int = int(os.getenv("FETCH_TIMEOUT_SECONDS", "10"))
    FETCH_MAX_BYTES: int = int(os.getenv("FETCH_MAX_BYTES", str(1024 * 1024)))  # 1 MB
    LLM_BACKEND: str = os.getenv("LLM_BACKEND", "ollama")  # "ollama" or "disabled"


settings = Settings()
