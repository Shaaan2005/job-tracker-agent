"""Thin wrapper around the Ollama Python client."""

import json
import logging
from typing import Protocol

import ollama as ollama_client

from app.config import settings

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    """Protocol so we can swap in a fake for tests."""

    def chat(self, messages: list[dict]) -> str:
        """Send messages and return the assistant's text response."""
        ...


class OllamaLLM:
    """Production LLM client using Ollama."""

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
