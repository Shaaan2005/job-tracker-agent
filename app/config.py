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
    LLM_BACKEND: str = os.getenv("LLM_BACKEND", "ollama")  # "ollama", "remote", or "disabled"
    REMOTE_LLM_URL: str = os.getenv("REMOTE_LLM_URL") or os.getenv("OPENAI_BASE_URL", "https://api.groq.com/openai/v1")
    REMOTE_LLM_MODEL: str = os.getenv("REMOTE_LLM_MODEL", "llama-3.1-8b-instant")
    REMOTE_LLM_API_KEY: str = os.getenv("REMOTE_LLM_API_KEY") or os.getenv("OPENAI_API_KEY", "")


settings = Settings()
