"""Before-model callback that sanitizes LLM request content.

Acts as a catch-all defense layer, stripping invisible/control Unicode
characters from all text parts before they reach the model.  This
supplements per-tool sanitization (which is explicit and auditable) to
cover MCP tools and any other content paths that bypass tool-level
sanitization.
"""

import logging
from typing import Optional

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse

from radbot.tools.shared.sanitize import _get_sanitize_config, sanitize_text

logger = logging.getLogger(__name__)


def sanitize_before_model_callback(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> Optional[LlmResponse]:
    """Sanitize all text parts in the LLM request before sending to the model.

    Iterates over ``llm_request.contents`` and cleans every ``Part.text``
    in-place.  Returns ``None`` so the request proceeds normally.
    """
    cfg = _get_sanitize_config()
    if not cfg.get("callback_enabled", True) or not cfg.get("enabled", True):
        return None

    if not llm_request.contents:
        return None

    parts_cleaned = 0
    total_parts = 0
    details = []
    for ci, content in enumerate(llm_request.contents):
        if not content.parts:
            continue
        role = getattr(content, "role", "unknown")
        for pi, part in enumerate(content.parts):
            if hasattr(part, "text") and part.text:
                total_parts += 1
                cleaned = sanitize_text(
                    part.text,
                    source="before_model_callback",
                    strictness=cfg.get("strictness"),
                )
                if cleaned != part.text:
                    chars_removed = len(part.text) - len(cleaned)
                    details.append(
                        f"content[{ci}].parts[{pi}] (role={role}): "
                        f"removed {chars_removed} char(s)"
                    )
                    part.text = cleaned
                    parts_cleaned += 1

    if parts_cleaned:
        logger.info(
            "sanitize_callback: cleaned %d/%d part(s) — %s",
            parts_cleaned,
            total_parts,
            "; ".join(details),
        )

    return None
