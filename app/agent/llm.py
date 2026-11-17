"""Thin wrapper around LLM backends: local Ollama or OpenAI-compatible remote endpoints."""

import json
import logging
from typing import Protocol

import httpx
import ollama as ollama_client

from app.config import settings

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    """Protocol so we can swap in a fake for tests."""

    def chat(self, messages: list[dict]) -> str:
        """Send messages and return the assistant's text response."""
        ...


class OllamaLLM:
    """Production LLM client using local Ollama."""

    def __init__(self, model: str | None = None, host: str | None = None):
        self.model = model or settings.OLLAMA_MODEL
        self.host = host or settings.OLLAMA_HOST
        self._client = ollama_client.Client(host=self.host)

    def chat(self, messages: list[dict]) -> str:
        """Send a chat completion request and return the content string."""
        response = self._client.chat(model=self.model, messages=messages)
        content = response["message"]["content"]
        logger.debug("LLM response: %s", content[:200])
        return content


class RemoteLLM:
    """Production LLM client using an OpenAI-compatible remote endpoint (e.g. Groq, OpenRouter, Together AI)."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
    ):
        raw_url = (base_url or settings.REMOTE_LLM_URL).rstrip("/")
        if raw_url.endswith("/chat/completions"):
            self._endpoint = raw_url
        else:
            self._endpoint = f"{raw_url}/chat/completions"
        self.model = model or settings.REMOTE_LLM_MODEL
        self.api_key = api_key or settings.REMOTE_LLM_API_KEY
        if not self.api_key:
            raise ValueError(
                "Remote LLM API key is required. Set REMOTE_LLM_API_KEY or OPENAI_API_KEY in environment variables."
            )
        self._client = httpx.Client(timeout=60.0)

    def chat(self, messages: list[dict]) -> str:
        """Send chat messages to the remote endpoint and return the assistant response."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
        }
        resp = self._client.post(self._endpoint, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        logger.debug("Remote LLM response: %s", content[:200])
        return content


def get_llm_client() -> LLMClient:
    """Instantiate the configured LLM backend based on settings."""
    backend = settings.LLM_BACKEND.lower().strip()
    if backend == "remote":
        if not settings.REMOTE_LLM_API_KEY:
            raise ValueError(
                "Remote LLM backend selected, but REMOTE_LLM_API_KEY is not set."
            )
        return RemoteLLM()
    if backend == "ollama":
        return OllamaLLM()
    raise ValueError(f"LLM backend '{backend}' is disabled or unsupported.")
