"""Three-persona divergent ideation for Scout.

Fires three persona-scoped LLM calls in parallel — Pragmatic, Contrarian,
Wildcard — and returns their text outputs as a structured dict. Each call
has a strict 15-second timeout; if one persona fails or times out, the
other two still return and the failed slot carries an ``Error: ...`` string
so Scout can decide whether to retry, ignore, or surface it to the user.

Concurrency: Scout's tools are async (see `radbot/tools/council/critics.py`),
so we use ``asyncio.gather(..., return_exceptions=True)`` rather than a
thread pool. Each LLM call is wrapped in ``asyncio.wait_for`` for the
per-call timeout.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from google.adk.tools import FunctionTool
from google.genai import types as genai_types

from radbot.config import config_manager
from radbot.config.adk_config import create_client_with_config_settings
from radbot.tools.shared.sanitize import sanitize_external_content

logger = logging.getLogger(__name__)


PER_CALL_TIMEOUT_SECONDS = 15.0


# Persona prompts are encapsulated here — they must NOT leak into Scout's
# main system prompt. Each prompt asks for plain text (not JSON) so the
# tool can return prose that Scout can synthesise herself.
PERSONAS: Dict[str, Dict[str, str]] = {
    "pragmatic": {
        "result_key": "pragmatic_path",
        "system": (
            "You are the Pragmatic strategist. Propose the most direct, "
            "low-risk path to solving the problem using well-understood, "
            "battle-tested approaches. Optimise for shipping something that "
            "works in the next sprint. Prefer existing tools and patterns "
            "over novelty. Be concrete: name specific steps, libraries, or "
            "components. 4-8 sentences."
        ),
    },
    "contrarian": {
        "result_key": "contrarian_path",
        "system": (
            "You are the Contrarian. Argue the opposite of the obvious "
            "framing. Question the premise of the problem itself: is it the "
            "right problem to solve? Identify hidden assumptions and propose "
            "a path that inverts them. Surface failure modes the optimist "
            "would miss. Be specific about what you would NOT do and why. "
            "4-8 sentences."
        ),
    },
    "wildcard": {
        "result_key": "wildcard_path",
        "system": (
            "You are the Wildcard. Propose an unconventional, lateral path "
            "drawn from a distant domain (biology, music, urban planning, "
            "game design, etc.). Embrace novelty over safety. The goal is "
            "to surface a perspective the Pragmatist and Contrarian would "
            "never reach. Make the analogy concrete and translate it back "
            "to the problem. 4-8 sentences."
        ),
    },
}


def _model() -> str:
    """Resolve the model used for the three ideation calls.

    Mirrors `radbot/tools/council/critics.py::_council_model` — Scout's
    configured model with a fall-back to the main model.
    """
    try:
        return config_manager.get_agent_model("scout_agent")
    except Exception:
        return config_manager.get_main_model()


def _build_prompt(system: str, problem_statement: str) -> str:
    return (
        f"{system}\n\n"
        f"Problem statement:\n{problem_statement}\n\n"
        "Respond with plain prose only — no headings, no JSON, no preamble."
    )


async def _run_persona(
    persona_key: str,
    problem_statement: str,
) -> str:
    """Run a single persona call. Returns the text on success.

    Raises on failure — the caller wraps the call in ``asyncio.wait_for``
    and ``asyncio.gather(..., return_exceptions=True)`` so exceptions are
    captured and translated into per-slot error strings, never crashing
    the parent tool.
    """
    persona = PERSONAS[persona_key]
    prompt = _build_prompt(persona["system"], problem_statement)
    model = _model()

    client = create_client_with_config_settings()
    response = await client.aio.models.generate_content(
        model=model,
        contents=prompt,
        config=genai_types.GenerateContentConfig(temperature=0.9),
    )
    text = (response.text or "").strip()
    if not text:
        raise RuntimeError("empty response from model")
    return text


async def _run_persona_safe(persona_key: str, problem_statement: str) -> str:
    """Run a persona with a strict per-call timeout.

    Returns the persona's text on success, or an ``Error: ...`` string on
    timeout / exception. Never raises.
    """
    try:
        return await asyncio.wait_for(
            _run_persona(persona_key, problem_statement),
            timeout=PER_CALL_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("divergent_ideation: %s timed out", persona_key)
        return f"Error: Timeout after {PER_CALL_TIMEOUT_SECONDS:.0f}s"
    except Exception as e:  # noqa: BLE001 — graceful-degradation boundary
        logger.exception("divergent_ideation: %s failed", persona_key)
        return f"Error: {type(e).__name__}: {e}"


async def divergent_ideation(problem_statement: str) -> Dict[str, Any]:
    """Generate three parallel perspectives on a problem.

    Fires three persona-scoped LLM calls (Pragmatic, Contrarian, Wildcard)
    concurrently, each with a 15-second timeout. If a persona fails or
    times out, its slot contains an ``Error: ...`` string and the other
    two are still returned — the tool never raises.

    Args:
        problem_statement: A free-form description of the problem to ideate
            on. Sanitised at the boundary before being embedded in the
            persona prompts.

    Returns:
        ``{"pragmatic_path": str, "contrarian_path": str, "wildcard_path": str,
        "errors": [persona_key, ...]}`` — ``errors`` lists any persona keys
        whose slot is an error string, so callers can branch without parsing
        prose. Empty list when all three succeeded.
    """
    if not problem_statement or not problem_statement.strip():
        return {
            "pragmatic_path": "Error: empty problem statement",
            "contrarian_path": "Error: empty problem statement",
            "wildcard_path": "Error: empty problem statement",
            "errors": ["pragmatic", "contrarian", "wildcard"],
        }

    safe_problem = sanitize_external_content(
        problem_statement,
        source="divergent_ideation.problem",
        strictness="strict",
    )

    persona_keys = ("pragmatic", "contrarian", "wildcard")
    results = await asyncio.gather(
        *(_run_persona_safe(k, safe_problem) for k in persona_keys),
        return_exceptions=False,
    )

    out: Dict[str, Any] = {}
    errors: list[str] = []
    for key, text in zip(persona_keys, results):
        result_key = PERSONAS[key]["result_key"]
        out[result_key] = text
        if isinstance(text, str) and text.startswith("Error:"):
            errors.append(key)
    out["errors"] = errors
    return out


divergent_ideation_tool = FunctionTool(divergent_ideation)
