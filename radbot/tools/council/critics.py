"""FunctionTool critics for scout's plan council.

Four critics — three core + one on-demand — each a direct Gemini call that
returns structured findings. Scout invokes them in parallel per round and
synthesizes the output herself (no hidden aggregator).

See ``personas.py`` for lens definitions and the response schema.
See ``triggers.py`` for the "is this plan worth convening the council?"
heuristic.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from google.adk.tools import FunctionTool
from google.genai import types as genai_types

from radbot.config import config_manager
from radbot.config.adk_config import create_client_with_config_settings
from radbot.tools.council.personas import (
    CRITIC_RESPONSE_SCHEMA,
    PERSONAS,
    build_critic_prompt,
)
from radbot.tools.shared.sanitize import sanitize_external_content

logger = logging.getLogger(__name__)


def _council_model() -> str:
    """Resolve the model for council critics.

    Uses scout's configured model (same family as the orchestrator for v1).
    Cross-family routing via LiteLLM is PRJ1/PT18.
    """
    try:
        return config_manager.get_agent_model("scout_agent")
    except Exception:
        return config_manager.get_main_model()


async def _run_critic(
    persona_key: str,
    plan: str,
    prior_round_findings: Optional[str] = None,
) -> Dict[str, Any]:
    """Invoke a single critic and return normalized findings.

    Always returns a dict — errors surface as ``{"status": "error", ...}``
    so the tool caller (scout) can keep the council loop going and simply
    re-run a failed critic.
    """
    if persona_key not in PERSONAS:
        return {
            "status": "error",
            "message": f"unknown persona: {persona_key}",
        }

    # Sanitize inputs at the boundary — plan text can contain content pulled
    # in via wiki_read / web_fetch earlier in scout's turn, and we're about
    # to embed it in a new LLM prompt.
    safe_plan = sanitize_external_content(plan, source="council.plan", strictness="strict")
    safe_prior = (
        sanitize_external_content(
            prior_round_findings, source="council.prior", strictness="strict"
        )
        if prior_round_findings
        else None
    )

    prompt = build_critic_prompt(persona_key, safe_plan, safe_prior)
    model = _council_model()

    try:
        client = create_client_with_config_settings()
    except Exception as e:
        logger.error("Council: failed to construct genai client: %s", e)
        return {"status": "error", "message": f"genai client unavailable: {e}"}

    try:
        response = await client.aio.models.generate_content(
            model=model,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.3,
                response_mime_type="application/json",
                response_schema=CRITIC_RESPONSE_SCHEMA,
            ),
        )
    except Exception as e:
        logger.exception("Council: %s call failed", persona_key)
        return {"status": "error", "critic": persona_key, "message": str(e)}

    raw = (response.text or "").strip()
    if not raw:
        return {
            "status": "error",
            "critic": persona_key,
            "message": "empty response from model",
        }

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("Council: %s returned non-JSON: %s", persona_key, raw[:200])
        return {
            "status": "error",
            "critic": persona_key,
            "message": f"response was not valid JSON: {e}",
            "raw": raw[:500],
        }

    persona = PERSONAS[persona_key]
    return {
        "status": "success",
        "critic": persona_key,
        "persona_name": persona["name"],
        "persona_title": persona["title"],
        "verdict": parsed.get("verdict"),
        "findings": parsed.get("findings", []),
        "strengths": parsed.get("strengths", []),
        "model": model,
    }


# ── FunctionTool wrappers ───────────────────────────────────────────────────
#
# Each critic is a separate tool so scout can call them in parallel (Gemini
# supports parallel function-calling in a single turn). A shared
# _run_critic() would force sequencing — we want simultaneous review.


async def critique_architecture(
    plan: str,
    prior_round_findings: Optional[str] = None,
) -> Dict[str, Any]:
    """Archie — architect's review. Coherence, coupling, fit-with-existing-repo.

    Args:
        plan: Full plan text to critique. Include the 5-role context package
            if scout has assembled one.
        prior_round_findings: Optional markdown digest of other critics' Round 1
            findings, so Archie can cross-reference and disagree explicitly.
            Omit on Round 1.
    """
    return await _run_critic("archie", plan, prior_round_findings)


async def critique_safety(
    plan: str,
    prior_round_findings: Optional[str] = None,
) -> Dict[str, Any]:
    """Sentry — paranoid SRE. Blast radius, secrets, rollback, prod safety."""
    return await _run_critic("sentry", plan, prior_round_findings)


async def critique_feasibility(
    plan: str,
    prior_round_findings: Optional[str] = None,
) -> Dict[str, Any]:
    """Impl — senior IC. Scope realism, test strategy, what breaks at 2am."""
    return await _run_critic("impl", plan, prior_round_findings)


async def critique_ux_dx(
    plan: str,
    prior_round_findings: Optional[str] = None,
) -> Dict[str, Any]:
    """Echo — UX/DX advocate. Only convene for plans touching UI / CLI / DX.

    Scout decides to invoke this critic; it's not part of the default round.
    """
    return await _run_critic("ux_dx", plan, prior_round_findings)


critique_architecture_tool = FunctionTool(critique_architecture)
critique_safety_tool = FunctionTool(critique_safety)
critique_feasibility_tool = FunctionTool(critique_feasibility)
critique_ux_dx_tool = FunctionTool(critique_ux_dx)


# Core panel (the 3 convened for every plan that passes the trigger).
# UX/DX is opt-in — scout calls it only when the plan visibly touches
# UI / CLI / API / dev tooling.
COUNCIL_TOOLS = [
    critique_architecture_tool,
    critique_safety_tool,
    critique_feasibility_tool,
    critique_ux_dx_tool,
]
