"""After-model callback that repairs text-based tool calls from LLM responses.

Small/local models (e.g. Ollama qwen2.5:7b) sometimes output tool calls as
plain text instead of structured function calls.  For example::

    transfer_to_agent(agent_name="casa")

ADK's built-in fallback parser only catches JSON format::

    {"name": "transfer_to_agent", "arguments": {"agent_name": "casa"}}

This callback intercepts the LLM response and converts recognised text-based
tool calls into proper ``FunctionCall`` parts so ADK can process them.
"""

import logging
import re
from typing import Optional

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmResponse
from google.genai import types

logger = logging.getLogger(__name__)

# Pattern: function_name(key="value", key2="value2")
# Captures: group(1)=function_name, group(2)=arguments string
_FUNC_CALL_RE = re.compile(
    r"""
    \b(transfer_to_agent          # known ADK/agent function names
    |search_agent_memory
    |store_agent_memory
    |store_important_information
    |search_past_conversations
    )\s*\(\s*                      # opening paren
    ([^)]*?)                       # arguments (non-greedy)
    \s*\)                          # closing paren
    """,
    re.VERBOSE,
)

# Pattern for keyword arguments: key="value" or key='value'
_KWARG_RE = re.compile(
    r"""(\w+)\s*=\s*(?:"([^"]*)"|'([^']*)')""",
    re.VERBOSE,
)


def _parse_text_tool_call(text: str) -> Optional[types.FunctionCall]:
    """Try to extract a function call from text like ``func(arg="val")``.

    Returns a ``FunctionCall`` if a known function pattern is found,
    otherwise ``None``.
    """
    match = _FUNC_CALL_RE.search(text)
    if not match:
        return None

    func_name = match.group(1)
    args_str = match.group(2)

    # Parse keyword arguments
    args = {}
    for kwarg_match in _KWARG_RE.finditer(args_str):
        key = kwarg_match.group(1)
        value = kwarg_match.group(2) or kwarg_match.group(3) or ""
        args[key] = value

    return types.FunctionCall(name=func_name, args=args)


def tool_call_repair_after_model_callback(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> Optional[LlmResponse]:
    """Repair text-based tool calls in the LLM response.

    If the response contains only text parts that match known function call
    patterns, replace them with proper ``FunctionCall`` parts so ADK can
    process them as structured tool invocations.

    Returns ``None`` (pass-through) if no repair is needed, or a modified
    ``LlmResponse`` if text-based tool calls were found.
    """
    try:
        if not llm_response.content or not llm_response.content.parts:
            return None

        # Only act on non-partial, final responses
        if llm_response.partial:
            return None

        # Check if any text part contains a function call pattern
        repaired_parts = []
        any_repaired = False

        for part in llm_response.content.parts:
            # Skip non-text parts (already proper function calls, etc.)
            if not part.text:
                repaired_parts.append(part)
                continue

            func_call = _parse_text_tool_call(part.text)
            if func_call:
                # Replace the text part with a function call part
                repaired_parts.append(types.Part(function_call=func_call))
                any_repaired = True
                logger.info(
                    "Repaired text-based tool call: %s(%s) -> FunctionCall",
                    func_call.name,
                    func_call.args,
                )
            else:
                repaired_parts.append(part)

        if not any_repaired:
            return None

        # Return modified response with repaired parts
        llm_response.content = types.Content(
            role="model",
            parts=repaired_parts,
        )
        return llm_response

    except Exception as e:
        logger.debug("Tool call repair callback error (non-fatal): %s", e)
        return None
