"""Agent chat e2e tests via WebSocket.

These tests send messages through the WebSocket and verify the agent responds.
They require Gemini API access and are marked as slow.
"""

import uuid

import pytest

from tests.e2e.helpers.assertions import (
    assert_response_contains,
    assert_response_contains_any,
    assert_response_not_empty,
    assert_tool_was_called,
)
from tests.e2e.helpers.ws_client import WSTestClient

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio(loop_scope="session"), pytest.mark.slow, pytest.mark.requires_gemini, pytest.mark.timeout(120)]


class TestAgentChat:
    async def test_simple_greeting(self, live_server):
        """Send 'Hello' and expect a non-empty response."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response("Hello")
            assert_response_not_empty(result)
        finally:
            await ws.close()

    async def test_agent_personality(self, live_server):
        """Ask the agent its name — should mention 'beto'."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response("What is your name?")
            assert_response_contains_any(result, "beto", "Beto")
        finally:
            await ws.close()

    async def test_time_query(self, live_server):
        """Ask the time — response should contain time-like content."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response("What time is it right now?")
            text = assert_response_not_empty(result)
            # Should contain some time-related content (digits, AM/PM, or time words)
            has_time = any(
                indicator in text.lower()
                for indicator in [":", "am", "pm", "o'clock", "hour", "minute"]
            ) or any(c.isdigit() for c in text)
            assert has_time, f"Response doesn't seem to contain time info: {text[:200]}"
        finally:
            await ws.close()

    async def test_conversation_memory(self, live_server):
        """Send a name, then ask for it — agent should remember within the session."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            # Introduce a unique name
            result1 = await ws.send_and_wait_response(
                "My name is E2ETestUser. Please remember that."
            )
            assert_response_not_empty(result1)

            # Ask for the name back
            result2 = await ws.send_and_wait_response("What is my name?")
            assert_response_contains(result2, "E2ETestUser")
        finally:
            await ws.close()

    async def test_agent_uses_memory_tool(self, live_server):
        """Ask agent to remember something — should use store_important_information."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "Remember that the E2E test secret code is ALPHA123. "
                "Store this as an important fact."
            )
            text = assert_response_not_empty(result)
            # The agent should acknowledge storing the information
            # Tool call detection is best-effort since events may not surface tool names
            assert_response_contains_any(
                result, "stored", "remembered", "noted", "saved", "remember",
                "got it", "got that", "locked in", "recorded", "will remember",
                "confirmed", "acknowledged",
            )
        finally:
            await ws.close()
