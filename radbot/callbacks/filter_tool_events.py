"""Before-model callback that drops tool events from the root agent's
LLM prompt.

### Why

Beto is a pure orchestrator: its only tools are agent-scoped memory, and
its own output is almost always a short routing decision. Sub-agents do
all the real tool work. But the ADK session beto shares with its
sub-agents retains every ``function_call`` and ``function_response`` event
those sub-agents emit, and those events flow into beto's next LLM call as
part of ``llm_request.contents``.

Tool-response blobs (e.g. a full HA entity list, a calendar query dump)
can be tens of thousands of tokens each, change every turn, and are
useless to beto — it doesn't need to re-read the raw HA state to pick
which sub-agent to route to next. They also destroy prompt caching,
because the stable cacheable prefix (instructions + tools) becomes a tiny
fraction of a prompt dominated by churning tool blobs.

Measured in production (April 2026): beto averaged 149K prompt tokens per
call with only 2K cached — a 1.3% cache hit rate, vs. 66-82% for
sub-agents that have their context scoped. The gap is almost entirely
tool events.

### What

This callback drops ``Content`` entries from ``llm_request.contents`` whose
parts are only ``function_call`` and/or ``function_response`` — i.e. no
text for the LLM to read. User and assistant text survives unchanged, so
conversational coherence is preserved across turns.

Runs ``before_model_callback``, so it only affects the outgoing LLM
request. ``session.events`` is untouched, leaving ADK's internal state
tracking intact.

Attach this to the **root agent only**. Sub-agents already have
``scope_sub_agent_context_callback`` which trims to the current user
turn and so don't need this.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _has_text_part(content: Any) -> bool:
    """True when a Content has at least one part with non-empty text."""
    try:
        for part in getattr(content, "parts", None) or []:
            if getattr(part, "text", None):
                return True
        return False
    except Exception:
        return False


def filter_tool_events_from_prompt(
    callback_context: Any,
    llm_request: Any,
) -> Optional[Any]:
    """Drop tool-only Content entries from ``llm_request.contents``.

    Returns ``None`` so the filtered request proceeds to the model.
    """
    try:
        contents = getattr(llm_request, "contents", None)
        if not contents:
            return None

        original = len(contents)
        filtered = [c for c in contents if _has_text_part(c)]

        if len(filtered) == original:
            return None

        llm_request.contents = filtered
        logger.debug(
            "filter-tool-events: trimmed llm_request.contents %d → %d",
            original,
            len(filtered),
        )
    except Exception as e:
        logger.debug("filter-tool-events callback error (non-fatal): %s", e)
    return None
