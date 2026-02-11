"""After-model callback that records token usage telemetry.

Read-only observer — never modifies the LLM response.  Failures are
logged and swallowed so telemetry issues never affect agent operation.
"""

import logging
from typing import Optional

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmResponse

logger = logging.getLogger(__name__)


def telemetry_after_model_callback(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> Optional[LlmResponse]:
    """Record token usage from the model response into the usage tracker.

    Returns ``None`` so the response passes through unmodified.
    """
    try:
        usage = llm_response.usage_metadata
        if not usage:
            return None

        prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
        cached_tokens = getattr(usage, "cached_content_token_count", 0) or 0
        output_tokens = getattr(usage, "candidates_token_count", 0) or 0

        # Determine agent name from the callback context
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

        # Determine model name
        model = ""
        try:
            if hasattr(callback_context, "_invocation_context") and hasattr(
                callback_context._invocation_context, "agent"
            ):
                model = (
                    getattr(callback_context._invocation_context.agent, "model", "")
                    or ""
                )
        except Exception:
            pass

        from radbot.telemetry.usage_tracker import usage_tracker

        usage_tracker.record(
            prompt_tokens=prompt_tokens,
            cached_tokens=cached_tokens,
            output_tokens=output_tokens,
            agent_name=agent_name,
            model=model,
        )

        if cached_tokens > 0:
            logger.debug(
                "Telemetry: agent=%s prompt=%d cached=%d output=%d (%.0f%% cache hit)",
                agent_name,
                prompt_tokens,
                cached_tokens,
                output_tokens,
                (cached_tokens / prompt_tokens * 100) if prompt_tokens else 0,
            )
    except Exception as e:
        logger.debug("Telemetry callback error (non-fatal): %s", e)

    return None
