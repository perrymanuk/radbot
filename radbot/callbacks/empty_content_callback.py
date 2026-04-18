"""Callbacks to handle Gemini API empty content responses.

The Gemini API intermittently returns Content(role='model', parts=None) --
empty model responses with no text.  This is a well-documented issue affecting
all Gemini models (google/adk-python#3525, googleapis/python-genai#1289).

Root causes include:
- MALFORMED_FUNCTION_CALL silently normalized to finish_reason=STOP
- max_output_tokens truncation returning parts=None
- Silent safety filter triggers
- Transient API-side failures

These callbacks provide two layers of defense:
1. before_model: scrub empty Content from request history to prevent poisoning
2. after_model: detect empty responses and return a retry prompt
"""

import logging
from typing import Optional

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse

logger = logging.getLogger(__name__)


def scrub_empty_content_before_model(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> Optional[LlmResponse]:
    """Remove empty Content objects from the request history.

    Empty Content (parts=None or parts=[]) in the session history causes
    cascading failures where subsequent model calls also return empty.
    This scrubs them out before each model call.

    **Safety guard**: never leaves ``contents`` empty. If every entry
    looks empty (happens in ADK V1 right after ``transfer_to_agent`` —
    the sub-agent's first LLM request can carry scaffolding-only
    Content objects), we leave the request untouched and let ADK / the
    model handle it. Reducing ``contents`` to ``[]`` triggers the
    google-genai transformer's ``ValueError('contents are required.')``
    and kills the request outright, which is a worse failure mode than
    passing through.

    Returns None so the request proceeds normally.
    """
    if not llm_request.contents:
        return None

    original_count = len(llm_request.contents)
    cleaned = []
    removed = 0

    for content in llm_request.contents:
        # Keep content that has actual parts with data
        if content.parts is not None and len(content.parts) > 0:
            cleaned.append(content)
        else:
            removed += 1

    if removed > 0 and cleaned:
        llm_request.contents = cleaned
        logger.info(
            "empty_content_scrub: removed %d/%d empty Content objects from request history",
            removed,
            original_count,
        )
    elif removed > 0 and not cleaned:
        # Would have emptied contents entirely — pass through instead.
        logger.warning(
            "empty_content_scrub: %d Content objects all had empty parts; "
            "passing through untouched to avoid 'contents are required' 400",
            original_count,
        )

    return None


def handle_empty_response_after_model(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> Optional[LlmResponse]:
    """Detect empty model responses and return a retry prompt.

    When the model returns Content with parts=None, this callback returns
    a synthetic response asking the model to try again, rather than letting
    the empty content enter the session history and poison subsequent calls.

    Returns None if the response is normal (pass-through).
    Returns an LlmResponse with a retry prompt if the response is empty.
    """
    if not llm_response or not llm_response.content:
        return None

    content = llm_response.content

    # Check if content has actual parts with data
    has_content = False
    if content.parts is not None:
        for part in content.parts:
            if hasattr(part, "text") and part.text:
                has_content = True
                break
            if hasattr(part, "function_call") and part.function_call:
                has_content = True
                break
            if hasattr(part, "function_response") and part.function_response:
                has_content = True
                break

    if has_content:
        return None

    # Empty content detected -- determine agent context for logging
    agent_name = "unknown"
    try:
        if hasattr(callback_context, "agent_name"):
            agent_name = callback_context.agent_name
        elif hasattr(callback_context, "_invocation_context") and hasattr(
            callback_context._invocation_context, "agent"
        ):
            agent_name = callback_context._invocation_context.agent.name
    except Exception:
        pass

    logger.warning(
        "empty_content_callback: detected empty model response from agent '%s' "
        "(parts=%s) -- nullifying content to let session runner retry",
        agent_name,
        content.parts,
    )

    # Nullify the content so ADK's built-in guard at _postprocess_async drops it
    # silently (no event yielded → run_async loop breaks → session runner sees no
    # text → triggers retry with fresh session). Do NOT return a synthetic
    # LlmResponse — ADK treats that as the final answer with no retry path.
    llm_response.content = None
    return None
