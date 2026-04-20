"""Before-model callback that injects Telos context into beto's prompt.

Two-tier injection:

* Tier 1 — anchor (~300B, capped at 500): appended to
  ``llm_request.config.system_instruction`` on EVERY turn. Keeps beto
  grounded in identity + mission + pointer to tools.

* Tier 2 — full block (~2KB, capped at 2048): appended to
  ``llm_request.config.system_instruction`` on the FIRST turn of each
  session only, gated by ``callback_context.state["telos_bootstrapped"]``.
  Subsequent turns in the same session drop it to save context window.

  (Per-turn re-injection is unnecessary because once the model has seen
  the full block in a session, the ensuing conversation history keeps it
  fresh in-context. If ADK compacts old turns, the anchor remains.)

Attach to beto's ``before_model_callback`` list only. Do NOT add to the
shared ``_before_cbs`` used by sub-agents — sub-agents are tool executors
and don't need user persona context.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_BOOTSTRAP_STATE_KEY = "telos_bootstrapped"


def inject_telos_context(callback_context: Any, llm_request: Any) -> Optional[Any]:
    """Inject Telos tiers into ``llm_request.config.system_instruction``.

    Returns ``None`` so the modified request proceeds to the model.
    """
    try:
        from .loader import build_telos_tiers

        anchor, full_block = build_telos_tiers()
        if not anchor and not full_block:
            return None  # empty Telos — no-op

        # Session-start gate: first turn gets anchor + full block;
        # subsequent turns get anchor only.
        state = _get_state(callback_context)
        is_first_turn = not state.get(_BOOTSTRAP_STATE_KEY)

        if is_first_turn and full_block:
            injection = f"{anchor}\n\n{full_block}" if anchor else full_block
            try:
                state[_BOOTSTRAP_STATE_KEY] = True
            except Exception as e:
                logger.debug("could not set telos bootstrap state flag: %s", e)
        else:
            injection = anchor

        if injection:
            _append_to_system_instruction(llm_request, injection)
            _record_injection_telemetry(
                anchor=anchor or "",
                full_block=full_block if (is_first_turn and full_block) else "",
                injection=injection,
                is_first_turn=bool(is_first_turn and full_block),
            )
    except Exception as e:
        logger.warning("inject_telos_context error (non-fatal): %s", e)
    return None


def _approx_tokens(text: str) -> int:
    """Crude token estimate (~4 chars/token). Cheap, no tokenizer dependency."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def _record_injection_telemetry(
    *, anchor: str, full_block: str, injection: str, is_first_turn: bool
) -> None:
    """Enqueue Telos context-injection token counts. Never raises."""
    try:
        from radbot.tools.telemetry import get_telemetry_service

        get_telemetry_service().enqueue(
            "context_injection",
            {
                "anchor_tokens": _approx_tokens(anchor),
                "full_block_tokens": _approx_tokens(full_block),
                "total_tokens": _approx_tokens(injection),
                "is_first_turn": bool(is_first_turn),
            },
        )
    except Exception as e:
        logger.debug("context-injection telemetry enqueue failed (non-fatal): %s", e)


def _get_state(callback_context: Any) -> Any:
    """Access callback_context.state defensively."""
    state = getattr(callback_context, "state", None)
    if state is None:
        return {}
    return state


def _append_to_system_instruction(llm_request: Any, text: str) -> None:
    """Append text to ``llm_request.config.system_instruction``.

    ADK passes a ``google.genai.types.GenerateContentConfig`` as
    ``llm_request.config``. ``system_instruction`` on that config may be
    ``None``, a ``str``, or a ``Content``. We coerce to string and append.
    """
    config = getattr(llm_request, "config", None)
    if config is None:
        return
    existing = getattr(config, "system_instruction", None)
    if existing is None:
        config.system_instruction = text
        return
    if isinstance(existing, str):
        config.system_instruction = f"{existing}\n\n{text}"
        return
    # Content-like: try to extract text from parts.
    existing_text = _content_to_text(existing)
    config.system_instruction = f"{existing_text}\n\n{text}" if existing_text else text


def _content_to_text(content: Any) -> str:
    """Best-effort string extraction from a Content-like object."""
    try:
        parts = getattr(content, "parts", None) or []
        chunks = []
        for part in parts:
            t = getattr(part, "text", None)
            if t:
                chunks.append(t)
        return "\n".join(chunks)
    except Exception:
        return ""
