"""Before-model callback that scopes a sub-agent's LLM context to the
current user turn only.

### Why

Sub-agents share the ADK ``Session`` with the root orchestrator. By default
that means every sub-agent sees the full conversation history, which causes
two failure modes:

1. **Context bleed:** Casa, asked to turn off a light, also sees that an
   earlier turn asked for movie recommendations, and volunteers media cards
   it wasn't asked for.
2. **Context bloat:** each sub-agent's prompt grows linearly with session
   length, burning tokens that aren't load-bearing for the task at hand.

### What

This callback runs right before a sub-agent's LLM invocation. It finds the
boundary of the current user turn (the most recent ``Content`` with
``role='user'`` whose parts include actual text, not just a
``function_response``) and drops everything before it from
``llm_request.contents``.

What remains:
  * the current user message
  * any model output since then (e.g. the sub-agent's own in-flight tool calls)
  * any function_response parts from the current invocation

What gets dropped:
  * every prior user/assistant turn
  * every prior invocation's tool activity

The sub-agent's system instruction and registered tools are unaffected —
those live on ``llm_request.config``, not ``llm_request.contents``.

**Do not** attach this to the root agent (Beto). Beto is the user's
conversational partner and needs the full history to stay coherent across
turns.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _is_user_text(content: Any) -> bool:
    """True when a Content represents an actual user message (not a
    function_response disguised as role='user')."""
    try:
        if getattr(content, "role", None) != "user":
            return False
        for part in getattr(content, "parts", None) or []:
            if getattr(part, "text", None):
                return True
        return False
    except Exception:
        return False


def scope_sub_agent_context_callback(
    callback_context: Any,
    llm_request: Any,
) -> Optional[Any]:
    """Trim ``llm_request.contents`` to the current user turn.

    Returns ``None`` so the trimmed request proceeds to the model.
    """
    try:
        contents = getattr(llm_request, "contents", None)
        if not contents or len(contents) < 2:
            return None

        # Walk from the end to find the last user text turn.
        last_user_idx: Optional[int] = None
        for i in range(len(contents) - 1, -1, -1):
            if _is_user_text(contents[i]):
                last_user_idx = i
                break

        if last_user_idx is None or last_user_idx == 0:
            return None  # nothing to strip

        trimmed = contents[last_user_idx:]
        agent_name = "unknown"
        try:
            inv = getattr(callback_context, "_invocation_context", None)
            if inv and getattr(inv, "agent", None):
                agent_name = inv.agent.name
        except Exception:
            pass
        logger.debug(
            "scope-to-turn: agent=%s trimmed llm_request.contents %d → %d",
            agent_name,
            len(contents),
            len(trimmed),
        )
        llm_request.contents = trimmed
    except Exception as e:
        logger.debug("scope-to-turn callback error (non-fatal): %s", e)
    return None
