"""Hand-written agent loop – no LangChain.

The loop builds a prompt describing available tools, sends it to the LLM,
parses the JSON response, dispatches to the matching tool, records each
step, and repeats until the model says "finish" or the step cap is reached.
"""

import json
import logging

from sqlalchemy.orm import Session

from app.agent import tools
from app.agent.llm import LLMClient
from app.config import settings
from app.db import queries
from app.db.models import AgentRunStatus
from app.schemas import AgentStep, ToolCall

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a job-application tracking assistant. You have access to these tools:

1. extract_posting_fields(text: str) -> dict
   Extracts structured fields (company, role_title, location, deadline, required_skills) from job-posting text.
   If raw job posting text is provided in the prompt, you MUST call this tool first. Do NOT call fetch_posting.

2. fetch_posting(url: str) -> str
   Fetches and cleans text from a job-posting URL. Only call this if you were given an http(s) URL. If you already have the job posting text, do NOT call this tool.

3. match_skills(required_skills: list[str]) -> dict
   Compares the required skills against the user's profile; returns matched, missing, and score.
   Call this after extract_posting_fields.

4. save_application(fields: dict) -> int
   Saves the application to the database and returns its id. The `fields` dict
   must include: company, role_title, location, deadline, required_skills,
   matched_skills, missing_skills, match_score, source_text, and optionally source_url.
   Call this after match_skills.

5. finish(application_id: int) -> void
   When save_application has returned an application_id, call this to complete the workflow.

Standard workflow order:
- If text is provided: extract_posting_fields -> match_skills -> save_application -> finish
- If URL is provided: fetch_posting -> extract_posting_fields -> match_skills -> save_application -> finish

Reply with ONLY valid JSON on every turn – no markdown, no explanation:
{"tool": "<tool_name>", "arguments": {<args>}}

When you have finished all steps, reply:
{"tool": "finish", "arguments": {"application_id": <id>}}
"""


class AgentError(Exception):
    """Raised when the agent loop fails irrecoverably."""


async def run_agent(
    llm: LLMClient,
    db: Session,
    posting_text: str | None = None,
    posting_url: str | None = None,
) -> tuple[int, list[AgentStep]]:
    """Execute the agent loop, persist the run, and return (application_id, steps).

    Args:
        llm: An object satisfying the LLMClient protocol.
        db: SQLAlchemy session.
        posting_text: Raw posting text (mutually exclusive with posting_url).
        posting_url: URL to fetch (mutually exclusive with posting_text).

    Returns:
        Tuple of (application_id, list_of_steps).

    Raises:
        AgentError: When the agent exceeds step cap or fails to produce a result.
    """
    max_steps = settings.MAX_AGENT_STEPS
    steps: list[AgentStep] = []
    total_json_retries = 0

    run_record = queries.create_agent_run(db)

    # Build initial user message
    if posting_text:
        user_msg = f"Process this job posting (raw text provided below). Call extract_posting_fields directly:\n\n{posting_text}"
    elif posting_url:
        user_msg = f"Process this job posting URL: {posting_url}"
    else:
        queries.finish_agent_run(
            db,
            run_id=run_record.id,
            status=AgentRunStatus.error,
            steps=[],
            application_id=None,
            json_retries=0,
        )
        raise AgentError("Either posting_text or posting_url is required")

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]

    context = {
        "source_text": posting_text or "",
        "source_url": posting_url,
        "extracted_fields": None,
        "matched_skills_result": None,
        "saved_application_id": None,
    }

    try:
        for step_num in range(1, max_steps + 1):
            raw = llm.chat(messages)
            tool_call, retries = _parse_tool_call(raw, llm, messages)
            total_json_retries += retries

            if tool_call is None:
                raise AgentError("Failed to parse LLM response after retry")

            logger.info(
                "Agent step %d: tool=%s args_keys=%s",
                step_num,
                tool_call.tool,
                list(tool_call.arguments.keys()),
            )

            # ── Finish? ───────────────────────────────────────────────────────
            if tool_call.tool == "finish":
                app_id = (
                    tool_call.arguments.get("application_id")
                    or context["saved_application_id"]
                )
                if app_id is not None:
                    steps.append(
                        AgentStep(
                            tool="finish",
                            arguments={"application_id": int(app_id)},
                            result_summary=f"Finished. application_id={app_id}",
                        )
                    )
                    serialized_steps = [s.model_dump() for s in steps]
                    queries.finish_agent_run(
                        db,
                        run_id=run_record.id,
                        status=AgentRunStatus.success,
                        steps=serialized_steps,
                        application_id=int(app_id),
                        json_retries=total_json_retries,
                    )
                    return int(app_id), steps
                raise AgentError("Agent finished without returning application_id")

            # ── Dispatch tool ─────────────────────────────────────────────────
            result, summary = await _dispatch(
                tool_call, llm, messages, db, context
            )

            steps.append(
                AgentStep(
                    tool=tool_call.tool,
                    arguments=_safe_args(tool_call),
                    result_summary=summary,
                )
            )

            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": f"Tool result:\n{json.dumps(result, default=str)}",
                }
            )

        serialized_steps = [s.model_dump() for s in steps]
        queries.finish_agent_run(
            db,
            run_id=run_record.id,
            status=AgentRunStatus.step_cap,
            steps=serialized_steps,
            application_id=None,
            json_retries=total_json_retries,
        )
        raise AgentError(f"Agent exceeded maximum steps ({max_steps})")

    except AgentError:
        serialized_steps = [s.model_dump() for s in steps]
        queries.finish_agent_run(
            db,
            run_id=run_record.id,
            status=AgentRunStatus.step_cap if len(steps) >= max_steps else AgentRunStatus.error,
            steps=serialized_steps,
            application_id=None,
            json_retries=total_json_retries,
        )
        raise
    except Exception as exc:
        serialized_steps = [s.model_dump() for s in steps]
        queries.finish_agent_run(
            db,
            run_id=run_record.id,
            status=AgentRunStatus.error,
            steps=serialized_steps,
            application_id=None,
            json_retries=total_json_retries,
        )
        raise AgentError(f"Unexpected agent error: {exc}") from exc


def _parse_tool_call(
    raw: str, llm: LLMClient, messages: list[dict]
) -> tuple[ToolCall | None, int]:
    """Parse LLM output as a ToolCall. Retry once on failure.

    Returns:
        tuple (ToolCall or None, retry_count)
    """
    retries = 0
    decoder = json.JSONDecoder()
    for attempt in range(2):
        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                lines = cleaned.splitlines()
                lines = [l for l in lines if not l.strip().startswith("```")]
                cleaned = "\n".join(lines).strip()

            # Extract first JSON object starting from first '{'
            idx = cleaned.find("{")
            if idx != -1:
                cleaned = cleaned[idx:]

            data, _ = decoder.raw_decode(cleaned)
            return ToolCall.model_validate(data), retries
        except Exception as exc:
            if attempt == 0:
                retries += 1
                logger.warning("JSON parse failed (%s), retrying", exc)
                messages.append({"role": "assistant", "content": raw})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Your response was not valid JSON: {exc}. "
                            "Please reply with ONLY valid JSON: {\"tool\": \"...\", \"arguments\": {...}}"
                        ),
                    },
                )
                raw = llm.chat(messages)
            else:
                logger.error("JSON parse failed on retry: %s", exc)
                return None, retries
    return None, retries


async def _dispatch(
    tool_call: ToolCall,
    llm: LLMClient,
    messages: list[dict],
    db: Session,
    context: dict,
) -> tuple[dict | str, str]:
    """Call the named tool and return (result, summary_string)."""
    name = tool_call.tool
    args = tool_call.arguments

    if name == "fetch_posting":
        if context["source_text"] and not context["source_url"]:
            return (
                "Error: Job posting text is already provided in the prompt. Do NOT call fetch_posting. Call extract_posting_fields directly on the provided text.",
                "fetch_posting rejected: text already provided",
            )
        url = args.get("url", "")
        if not url or not (url.startswith("http://") or url.startswith("https://")):
            return (
                f"FetchError: Invalid URL scheme for {url!r}. URLs must begin with http:// or https://. If raw text is provided, call extract_posting_fields.",
                f"fetch_posting rejected: invalid URL {url!r}",
            )
        result = await tools.fetch_posting(url)
        if isinstance(result, str) and not result.startswith("FetchError"):
            context["source_text"] = result
        return result, f"Fetched {len(result)} chars from {url}"

    if name == "extract_posting_fields":
        if context["extracted_fields"] is not None:
            return (
                {
                    "status": "already_extracted",
                    "extracted_fields": context["extracted_fields"],
                    "message": "Fields have already been extracted. Next step: call match_skills with required_skills.",
                },
                "Fields already extracted",
            )
        # Always use the complete posting text if available in context to prevent LLM truncation
        text = context["source_text"] if context["source_text"] else args.get("text", "")
        result = tools.extract_posting_fields(text, llm, messages)
        context["extracted_fields"] = result
        return (
            {
                **result,
                "next_step": "Call match_skills with the required_skills list.",
            },
            f"Extracted {len(result.get('required_skills', []))} skills",
        )

    if name == "match_skills":
        req = args.get("required_skills", [])
        if not req and context["extracted_fields"]:
            req = context["extracted_fields"].get("required_skills", [])
        elif req and context["extracted_fields"] and not context["extracted_fields"].get("required_skills"):
            context["extracted_fields"]["required_skills"] = req
        result = tools.match_skills_tool(req, db)
        context["matched_skills_result"] = result
        return (
            {
                **result,
                "next_step": "Call save_application with the application fields.",
            },
            f"Score={result['score']}",
        )

    if name == "save_application":
        if context["saved_application_id"] is not None:
            return (
                {
                    "application_id": context["saved_application_id"],
                    "message": f"Application {context['saved_application_id']} is already saved. Final step: call finish with application_id.",
                },
                f"Already saved application id={context['saved_application_id']}",
            )

        fields = dict(args.get("fields", {}))
        if context["extracted_fields"]:
            ef = context["extracted_fields"]
            fields.setdefault("company", ef.get("company", "Unknown"))
            fields.setdefault("role_title", ef.get("role_title", "Software Engineer Intern"))
            fields.setdefault("location", ef.get("location", ""))
            fields.setdefault("deadline", ef.get("deadline"))
            # Ensure verified extracted required_skills are used to prevent LLM hallucinations
            if ef.get("required_skills"):
                fields["required_skills"] = ef["required_skills"]
            elif not fields.get("required_skills") and args.get("required_skills"):
                fields["required_skills"] = args.get("required_skills")

        if context["matched_skills_result"]:
            mr = context["matched_skills_result"]
            fields.setdefault("matched_skills", mr.get("matched", []))
            fields.setdefault("missing_skills", mr.get("missing", []))
            fields.setdefault("match_score", mr.get("score", 0.0))
        else:
            req_skills = fields.get("required_skills", [])
            mr = tools.match_skills_tool(req_skills, db)
            context["matched_skills_result"] = mr
            fields.setdefault("matched_skills", mr.get("matched", []))
            fields.setdefault("missing_skills", mr.get("missing", []))
            fields.setdefault("match_score", mr.get("score", 0.0))

        fields.setdefault("source_text", context["source_text"])
        fields.setdefault("source_url", context["source_url"])

        app_id = tools.save_application(fields, db)
        context["saved_application_id"] = app_id
        return (
            {
                "application_id": app_id,
                "message": f"Application {app_id} saved successfully. Now call finish with application_id {app_id}.",
            },
            f"Saved application id={app_id}",
        )

    return (
        {
            "error": f"Unknown tool: {name}. Valid tools: extract_posting_fields, fetch_posting, match_skills, save_application, finish."
        },
        f"Unknown tool '{name}' called",
    )


def _safe_args(tool_call: ToolCall) -> dict:
    """Return arguments safe for logging (truncate long text values)."""
    safe = {}
    for k, v in tool_call.arguments.items():
        if isinstance(v, str) and len(v) > 100:
            safe[k] = v[:100] + "…"
        else:
            safe[k] = v
    return safe
