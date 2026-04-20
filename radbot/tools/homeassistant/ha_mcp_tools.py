"""Adapt Home Assistant MCP tools into ADK ``FunctionTool`` instances.

Fetches the tool catalog from HA's ``mcp_server`` at agent-construction
time, wraps each tool as a FunctionTool whose implementation forwards
the call through ``HAMcpClient.call_tool``. The set of available tools
depends on what the HA admin has exposed to Assist — 19 built-in intents
plus every user-exposed script. See the reference in
``docs/plans/ha_alias_learning.md`` for context on the exposure model.

Tool response shape: HA wraps every MCP response in a single text
content block whose body is a JSON-encoded ``{"success": bool, "result":
...}`` envelope. This module unwraps that before returning to the LLM
so the agent sees structured data, not a string.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional

from google.adk.tools import FunctionTool

from radbot.tools.homeassistant.ha_mcp_client import HAMcpClient

logger = logging.getLogger(__name__)


# ADK tool names must be a valid Python identifier. Users can name HA
# scripts almost anything (we've seen leading digits, spaces, non-ASCII),
# so sanitize on the radbot side while preserving the original name for
# the MCP ``tools/call`` request.
_VALID_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _sanitize_tool_name(name: str) -> str:
    if _VALID_IDENT.match(name):
        return name
    sanitized = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if sanitized and sanitized[0].isdigit():
        sanitized = "ha_" + sanitized
    return sanitized or "ha_tool"


def _unwrap_ha_envelope(text: Optional[str]) -> Any:
    """Decode HA's ``{"success": bool, "result": ...}`` wrapper.

    Returns the ``result`` value on success, a structured error dict on
    failure, or the raw text if it doesn't match the expected shape.
    """
    if text is None:
        return None
    try:
        envelope = json.loads(text)
    except (TypeError, ValueError):
        return text
    if not isinstance(envelope, dict):
        return envelope
    if "success" in envelope:
        if envelope["success"]:
            return envelope.get("result")
        return {
            "status": "error",
            "error": envelope.get("error") or envelope.get("result"),
        }
    return envelope


def _make_tool_caller(client: HAMcpClient, original_name: str) -> Callable[..., Any]:
    """Build the async callable that ADK will invoke for this tool.

    The closure captures the HA-side tool name so the sanitized ADK tool
    name still maps to the right MCP tool.
    """

    async def _call(**kwargs: Any) -> Any:
        # Drop None values — JSON schemas default missing optional fields,
        # but ADK sometimes passes them as None which HA then rejects.
        payload = {k: v for k, v in kwargs.items() if v is not None}
        try:
            text = await client.call_tool(original_name, payload)
        except Exception as e:
            logger.warning(
                "HA MCP call %s failed: %s (args=%s)",
                original_name,
                e,
                list(payload.keys()),
            )
            return {"status": "error", "error": str(e)}
        return _unwrap_ha_envelope(text)

    return _call


def _build_function_schema(
    tool_name: str, description: str, input_schema: Dict[str, Any]
) -> Dict[str, Any]:
    """Translate an MCP tool entry into ADK FunctionTool.function_schema."""
    params = input_schema if isinstance(input_schema, dict) else {}
    # MCP uses ``inputSchema`` with standard JSON-schema shape;
    # FunctionTool's function_schema expects ``parameters`` of the same
    # shape. Pass through. Ensure ``type`` is present for safety.
    if "type" not in params:
        params = {"type": "object", **params}
    return {
        "name": tool_name,
        "description": description or f"Home Assistant MCP tool: {tool_name}",
        "parameters": params,
    }


def build_ha_mcp_function_tools(client: HAMcpClient) -> List[FunctionTool]:
    """Fetch HA's MCP tool list and wrap each as an ADK FunctionTool.

    Runs a sync tool-discovery call at factory time. Each wrapped tool
    executes asynchronously at LLM runtime, inside ADK's event loop.
    """
    try:
        raw_tools = client.list_tools_sync()
    except Exception as e:
        logger.error("Failed to list HA MCP tools: %s", e)
        return []

    tools: List[FunctionTool] = []
    seen_names: set[str] = set()

    for entry in raw_tools:
        original_name = entry.get("name", "")
        if not original_name:
            continue

        adk_name = _sanitize_tool_name(original_name)
        if adk_name in seen_names:
            # Sanitization collision (e.g. two scripts with punctuation
            # that collapses to the same identifier). Disambiguate with
            # a suffix so both remain callable.
            suffix = 2
            while f"{adk_name}_{suffix}" in seen_names:
                suffix += 1
            adk_name = f"{adk_name}_{suffix}"
        seen_names.add(adk_name)

        schema = _build_function_schema(
            adk_name,
            entry.get("description", "") or "",
            entry.get("inputSchema") or {},
        )
        func = _make_tool_caller(client, original_name)
        func.__name__ = adk_name  # improves ADK/telemetry log clarity

        tools.append(FunctionTool(function=func, function_schema=schema))

    logger.info(
        "Loaded %d Home Assistant MCP tools (from %d raw entries)",
        len(tools),
        len(raw_tools),
    )
    return tools
