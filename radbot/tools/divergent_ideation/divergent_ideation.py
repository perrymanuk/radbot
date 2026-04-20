"""Divergent ideation tool.

Runs three parallel LLM streams against a problem statement using lateral
inhibition — each stream is constrained to a distinct mode of reasoning so
the agent gets genuinely divergent options rather than three paraphrases of
the obvious answer:

  * **standard**   — the straightforward / textbook approach
  * **contrarian** — forbidden from using the obvious approach
  * **wildcard**   — an extreme / biological / lateral alternative

Design constraints (from EX6):
  1. Parallel execution via ``asyncio.gather(..., return_exceptions=True)``
     so one failed stream does not sink the whole batch.
  2. Uses the repo's existing LLM client interface
     (:func:`radbot.config.adk_config.create_client_with_config_settings`) —
     does NOT instantiate a raw SDK client. This preserves global auth,
     telemetry, and Vertex/API-key switching.
  3. Structured JSON return so the agent can parse reliably.
  4. Per-stream structured logs (latency, status).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from google.adk.tools import FunctionTool

from radbot.config import config_manager
from radbot.config.adk_config import create_client_with_config_settings

logger = logging.getLogger(__name__)

STREAM_PROMPTS: Dict[str, str] = {
    "standard": (
        "You are solving the following problem using the most straightforward, "
        "standard, textbook approach. Be clear and concise. Return only the "
        "proposed approach, no preamble.\n\nProblem: {problem}"
    ),
    "contrarian": (
        "You are solving the following problem, but you are FORBIDDEN from "
        "proposing the most obvious or conventional approach. You must find a "
        "genuinely different angle — ideally one that inverts a common "
        "assumption. Return only the proposed approach, no preamble.\n\n"
        "Problem: {problem}"
    ),
    "wildcard": (
        "You are solving the following problem with an extreme, lateral, "
        "biologically-inspired, or otherwise unconventional approach. Chaos "
        "and surprise are encouraged as long as the proposal could plausibly "
        "be made to work. Return only the proposed approach, no preamble.\n\n"
        "Problem: {problem}"
    ),
}

DEFAULT_TIMEOUT_SECONDS = 60.0


async def _run_stream(
    client: Any,
    model: str,
    stream_name: str,
    prompt: str,
    timeout: float,
) -> str:
    """Run a single LLM stream. Raises on failure — caller handles via gather."""
    started = time.monotonic()
    try:
        response = await asyncio.wait_for(
            client.aio.models.generate_content(model=model, contents=prompt),
            timeout=timeout,
        )
        elapsed_ms = int((time.monotonic() - started) * 1000)
        text = (getattr(response, "text", None) or "").strip()
        usage = getattr(response, "usage_metadata", None)
        tokens = getattr(usage, "total_token_count", None) if usage else None
        logger.info(
            "divergent_ideation stream ok",
            extra={
                "stream": stream_name,
                "model": model,
                "latency_ms": elapsed_ms,
                "tokens": tokens,
                "status": "ok",
            },
        )
        return text
    except Exception as e:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        logger.warning(
            "divergent_ideation stream failed",
            extra={
                "stream": stream_name,
                "model": model,
                "latency_ms": elapsed_ms,
                "status": "error",
                "error_type": type(e).__name__,
                "error_message": str(e)[:200],
            },
        )
        raise


async def _execute_async(
    problem_statement: str,
    model: Optional[str] = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    """Core async implementation. Returns the structured result dict."""
    if not problem_statement or not problem_statement.strip():
        return {
            "status": "error",
            "message": "problem_statement must be a non-empty string",
        }

    try:
        client = create_client_with_config_settings()
    except Exception as e:
        logger.error(f"divergent_ideation: failed to build LLM client: {e}")
        return {
            "status": "error",
            "message": f"Failed to initialize LLM client: {e}",
        }

    resolved_model = model or config_manager.get_agent_model("scout_agent") or "gemini-2.5-flash"
    # Strip an "ollama_chat/" prefix etc.; genai client expects a bare model id.
    if "/" in resolved_model:
        resolved_model = resolved_model.split("/", 1)[1]

    stream_names = list(STREAM_PROMPTS.keys())
    coros = [
        _run_stream(
            client=client,
            model=resolved_model,
            stream_name=name,
            prompt=STREAM_PROMPTS[name].format(problem=problem_statement),
            timeout=timeout,
        )
        for name in stream_names
    ]

    results = await asyncio.gather(*coros, return_exceptions=True)

    output: Dict[str, Any] = {
        "status": "success",
        "problem_statement": problem_statement,
        "model": resolved_model,
    }
    any_success = False
    for name, result in zip(stream_names, results):
        if isinstance(result, BaseException):
            output[name] = {
                "error": type(result).__name__,
                "message": str(result)[:500],
            }
        else:
            output[name] = result
            any_success = True

    if not any_success:
        output["status"] = "error"
        output["message"] = "All ideation streams failed — see per-stream errors."

    return output


def execute_divergent_ideation(problem_statement: str) -> Dict[str, Any]:
    """Run three parallel divergent-ideation streams against a problem.

    Args:
        problem_statement: The problem to ideate on. Plain natural-language
            description; the tool wraps it with per-stream framing.

    Returns:
        A dict with keys ``status``, ``problem_statement``, ``model``, and
        one key per stream (``standard``, ``contrarian``, ``wildcard``).
        A successful stream's value is the raw LLM text; a failed stream's
        value is ``{"error": <type>, "message": <str>}``. Overall status
        is ``"success"`` if at least one stream succeeded, otherwise
        ``"error"``.
    """
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            # We're inside an already-running loop (e.g. ADK async tool
            # dispatch). Schedule and wait synchronously via a new loop in
            # a worker thread — matches how other sync-wrapping tools in
            # this repo deal with the same constraint.
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, _execute_async(problem_statement))
                return future.result()
    except RuntimeError:
        pass
    return asyncio.run(_execute_async(problem_statement))


execute_divergent_ideation_tool = FunctionTool(execute_divergent_ideation)
