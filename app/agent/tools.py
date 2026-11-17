"""Tool functions the agent can call.

Each tool is a plain Python function with typed arguments.  The agent
dispatches to these by name.
"""

import json
import logging
import re

from sqlalchemy.orm import Session

from app.db import queries
from app.schemas import ExtractedPostingFields, SkillsMatchResult
from app.services import posting_fetcher, skills_matcher

logger = logging.getLogger(__name__)


async def fetch_posting(url: str) -> str:
    """Fetch and clean text from a job-posting URL.
    
    Returns an error message rather than raising so the agent can inspect
    the result and decide how to recover.
    """
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return (
            f"FetchError: Invalid URL scheme for {url!r}. URLs must begin with http:// or https://. "
            "If the job posting text was already provided in the prompt, do NOT call fetch_posting; "
            "call extract_posting_fields directly on the provided text."
        )

    try:
        text = await posting_fetcher.fetch_posting(url)
        return text
    except Exception as exc:
        logger.warning("fetch_posting failed for URL %r: %s", url, exc)
        return f"FetchError: Failed to fetch {url!r}: {exc}. If raw text is available in context, use that instead."


def _parse_or_repair_json(raw: str, llm) -> dict | None:
    """Attempt parsing, cleaning, retrying, and regex extraction for LLM JSON."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()

    # 1. Try direct json.loads
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    # 2. Try raw_decode from first '{'
    idx = cleaned.find("{")
    if idx != -1:
        try:
            decoder = json.JSONDecoder()
            data, _ = decoder.raw_decode(cleaned[idx:])
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    # 3. Retry once with LLM to repair JSON
    try:
        repair_messages = [
            {
                "role": "system",
                "content": (
                    "You are a strict JSON repair utility. Fix the malformed JSON below and output ONLY "
                    "a valid JSON object with keys: company, role_title, location, deadline, required_skills."
                ),
            },
            {
                "role": "user",
                "content": f"Fix this malformed JSON and return ONLY the valid JSON object:\n\n{raw}",
            },
        ]
        repaired_raw = llm.chat(repair_messages).strip()
        if repaired_raw.startswith("```"):
            lines = repaired_raw.splitlines()
            lines = [l for l in lines if not l.strip().startswith("```")]
            repaired_raw = "\n".join(lines).strip()
        idx = repaired_raw.find("{")
        if idx != -1:
            decoder = json.JSONDecoder()
            data, _ = decoder.raw_decode(repaired_raw[idx:])
            if isinstance(data, dict):
                return data
    except Exception as exc:
        logger.warning("LLM JSON repair attempt failed: %s", exc)

    # 4. Regex fallback extraction
    return _regex_fallback_extract(raw)


def _regex_fallback_extract(raw: str) -> dict:
    """Extract fields using regex patterns if JSON parsing completely failed."""
    company_match = re.search(r'"company"\s*:\s*"([^"]+)"', raw)
    role_match = re.search(r'"role_title"\s*:\s*"([^"]+)"', raw)
    location_match = re.search(r'"location"\s*:\s*"([^"]+)"', raw)

    skills: list[str] = []
    skills_block = re.search(r'"required_skills"\s*:\s*\[(.*?)\]', raw, re.DOTALL)
    if skills_block:
        skills = re.findall(r'"([^"]+)"', skills_block.group(1))

    return {
        "company": company_match.group(1) if company_match else "Unknown",
        "role_title": role_match.group(1) if role_match else "Software Engineer Intern",
        "location": location_match.group(1) if location_match else "",
        "deadline": None,
        "required_skills": skills,
    }


def extract_posting_fields(text: str, llm, messages: list[dict]) -> dict:
    """Ask the LLM to extract structured fields from posting text.

    Sends a dedicated prompt, validates the reply with Pydantic, and returns
    the dict on success.
    """
    extraction_prompt = (
        "You are an expert technical recruiter. Analyze the job posting below and extract the structured fields.\n\n"
        "RULES FOR required_skills:\n"
        "- Extract ONLY technical skills (languages, frameworks, libraries, tools, technical concepts) that are REQUIRED or essential.\n"
        "- Do NOT include skills explicitly listed as 'bonus', 'nice to have', 'a plus', or 'preferred'.\n"
        "- Do NOT include general job duties, responsibilities, or activities (e.g. do NOT include 'Code optimization', 'Testing and debugging', 'Collaborative project work', 'Software development', 'Learning and growth').\n"
        "- If a skill name has 'development' or 'programming' appended to a language (e.g. 'Python development' or 'Python programming'), extract just the language name (e.g. 'Python').\n"
        "- Return ATOMIC, standalone names (e.g. ['Python', 'TypeScript', 'Docker', 'Kubernetes', 'Node.js', 'MongoDB', 'React', 'MERN stack', 'PyTorch', 'TensorFlow', 'Whisper', 'wav2vec2', 'HuBERT', 'Hugging Face Transformers', 'AWS', 'GCP', 'Azure', 'ASR', 'speech-to-speech', 'speech recognition']).\n"
        "- If an explicit 'Skills:' section exists at the end of the posting, include all skills listed there.\n"
        "- Do NOT invent skills that are not mentioned in this specific job posting.\n\n"
        "Output ONLY a single valid JSON object with this exact structure:\n"
        "{\n"
        '  "company": "Company Name",\n'
        '  "role_title": "Job Title",\n'
        '  "location": "Location string or empty string",\n'
        '  "deadline": "Deadline string or null",\n'
        '  "required_skills": ["Skill1", "Skill2"]\n'
        "}\n\n"
        f"Job posting:\n{text}"
    )

    extraction_messages = [
        {
            "role": "system",
            "content": (
                "You are a structured data extractor. You convert job postings into valid JSON objects. "
                "Output ONLY raw JSON with keys: company, role_title, location, deadline, required_skills. "
                "Do not wrap in tool-calling format."
            ),
        },
        {"role": "user", "content": extraction_prompt},
    ]

    raw = llm.chat(extraction_messages)
    data = _parse_or_repair_json(raw, llm)

    if not data or not isinstance(data, dict):
        data = _regex_fallback_extract(raw)

    # Unwrap if wrapped inside arguments or tool dict
    if "arguments" in data and isinstance(data["arguments"], dict) and "company" in data["arguments"]:
        data = data["arguments"]
    elif "tool" in data and "arguments" in data and isinstance(data["arguments"], dict):
        data = data["arguments"]

    # Normalize defaults
    if not data.get("company"):
        data["company"] = "Unknown"
    if not data.get("role_title"):
        data["role_title"] = "Software Engineer Intern"
    if not data.get("location"):
        data["location"] = ""
    if "required_skills" not in data or not isinstance(data["required_skills"], list):
        data["required_skills"] = []

    # Clean individual extracted skills
    generic_noise = {"stack", "skills", "skill", "tools", "tool", "technology", "technologies"}
    cleaned_skills = []
    for s in data["required_skills"]:
        if isinstance(s, str) and s.strip():
            # If comma-separated in a single string, split them
            parts = [p.strip() for p in s.split(",") if p.strip()] if ("," in s and len(s) > 15) else [s.strip()]
            for item in parts:
                if item.lower() not in generic_noise and item not in cleaned_skills:
                    cleaned_skills.append(item)
    data["required_skills"] = cleaned_skills

    parsed = ExtractedPostingFields.model_validate(data)
    return parsed.model_dump()


def match_skills_tool(required_skills: list[str], db: Session) -> dict:
    """Compare required skills against the user profile in the database."""
    profile = queries.get_profile(db)
    user_skills = profile.skills if profile else []
    result = skills_matcher.match_skills(required_skills, user_skills)
    return result


def save_application(fields: dict, db: Session) -> int:
    """Write an application to the database and return its id."""
    app = queries.create_application(db, **fields)
    return app.id
