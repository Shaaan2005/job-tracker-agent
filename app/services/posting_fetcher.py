"""Fetch and clean text from a URL or raw posting text."""

from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import settings


class FetchError(Exception):
    """Raised when URL fetching fails."""


def clean_html(html: str) -> str:
    """Strip HTML tags and return visible text."""
    soup = BeautifulSoup(html, "html.parser")
    # Remove script and style elements
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    # Collapse multiple blank lines
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def clean_text(raw: str) -> str:
    """Minimal cleaning for already-plain text."""
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    return "\n".join(lines)


async def fetch_posting(url: str) -> str:
    """Fetch a job posting URL and return cleaned plain text.

    Raises:
        FetchError: on timeout, size limit, or non-http(s) scheme.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise FetchError(f"Unsupported URL scheme: {parsed.scheme!r}")

    async with httpx.AsyncClient(
        timeout=settings.FETCH_TIMEOUT_SECONDS, follow_redirects=True
    ) as client:
        response = await client.get(url)
        response.raise_for_status()

        # Enforce size limit
        if len(response.content) > settings.FETCH_MAX_BYTES:
            raise FetchError(
                f"Response body exceeds {settings.FETCH_MAX_BYTES} bytes"
            )

    return clean_html(response.text)


def process_posting_input(
    posting_text: str | None, posting_url: str | None
) -> tuple[str, str | None]:
    """Return (cleaned_text, url_or_none) from whichever input was provided.

    For raw text this is synchronous; for URLs the caller must await
    ``fetch_posting`` separately.
    """
    if posting_text:
        return clean_text(posting_text), None
    if posting_url:
        # URL fetching is async – handled in the agent / route layer.
        return "", posting_url
    raise ValueError("Either posting_text or posting_url must be provided")
