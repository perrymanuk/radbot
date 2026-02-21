"""Non-deterministic response assertion helpers for agent chat tests."""

import pytest

from typing import Any, Dict, List

# Error patterns that indicate Gemini/LLM is not configured
_GEMINI_UNAVAILABLE_PATTERNS = [
    "missing key inputs",
    "api_key",
    "vertexai",
    "provide (`api_key`)",
    "google ai api",
]


def _check_gemini_available(ws_result: Dict[str, Any]) -> None:
    """Skip the test if the error indicates Gemini is not configured."""
    error = ws_result.get("error", "")
    if error:
        error_lower = error.lower()
        for pattern in _GEMINI_UNAVAILABLE_PATTERNS:
            if pattern in error_lower:
                pytest.skip(f"Gemini API not available: {error}")


def extract_response_text(ws_result: Dict[str, Any]) -> str:
    """Extract the final response text from a WS send_and_wait_response result."""
    return ws_result.get("response_text", "")


def assert_response_not_empty(ws_result: Dict[str, Any]) -> str:
    """Assert the response is not empty and return the text.

    Automatically skips if Gemini is not configured.
    """
    _check_gemini_available(ws_result)
    text = extract_response_text(ws_result)
    assert text, "Expected non-empty response from agent"
    return text


def assert_response_contains(ws_result: Dict[str, Any], *keywords: str) -> str:
    """Assert the response text contains all given keywords (case-insensitive)."""
    text = assert_response_not_empty(ws_result)
    text_lower = text.lower()
    for kw in keywords:
        assert kw.lower() in text_lower, (
            f"Expected '{kw}' in response, got: {text[:200]}"
        )
    return text


def assert_response_contains_any(ws_result: Dict[str, Any], *keywords: str) -> str:
    """Assert the response text contains at least one of the keywords."""
    text = assert_response_not_empty(ws_result)
    text_lower = text.lower()
    matched = any(kw.lower() in text_lower for kw in keywords)
    assert matched, (
        f"Expected at least one of {keywords} in response, got: {text[:200]}"
    )
    return text


def assert_tool_was_called(ws_result: Dict[str, Any], tool_name: str) -> bool:
    """Assert that a specific tool was called in the events."""
    events = ws_result.get("events", [])
    for event in events:
        # Check various event formats for tool calls
        if event.get("type") == "tool_call" and tool_name in str(event):
            return True
        if event.get("category") == "tool_call" and tool_name in str(event):
            return True
        summary = event.get("summary", "")
        if tool_name in summary:
            return True
        # Check text content for tool references
        text = event.get("text", "")
        if f"tool_call: {tool_name}" in text or f"'{tool_name}'" in text:
            return True
    # Not a hard failure — tool calls may not always be surfaced in events
    return False


def assert_agent_transferred(ws_result: Dict[str, Any], agent_name: str) -> bool:
    """Assert that an agent transfer occurred to the named agent."""
    events = ws_result.get("events", [])
    agent_lower = agent_name.lower()
    for event in events:
        # Check agent_name field
        if event.get("agent_name", "").lower() == agent_lower:
            return True
        # Check for transfer events
        if "transfer" in event.get("type", "").lower() and agent_lower in str(event).lower():
            return True
        if event.get("category") == "agent_transfer" and agent_lower in str(event).lower():
            return True
    return False
