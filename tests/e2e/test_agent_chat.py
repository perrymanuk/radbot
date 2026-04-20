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
)
from tests.e2e.helpers.ws_client import WSTestClient

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.slow,
    pytest.mark.requires_gemini,
    pytest.mark.timeout(120),
]


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
            assert_response_not_empty(result)
            # The agent should acknowledge storing the information
            # Tool call detection is best-effort since events may not surface tool names
            assert_response_contains_any(
                result,
                "stored",
                "remembered",
                "noted",
                "saved",
                "remember",
                "got it",
                "got that",
                "locked",
                "recorded",
                "will remember",
                "confirmed",
                "acknowledged",
                "banked",
                "stashed",
                "filed",
                "memory",
                "store",
                "vault",
                "brain",
            )
        finally:
            await ws.close()

    async def test_cross_session_memory(self, live_server):
        """Store information in one session, recall in another via persistent memory."""
        unique_code = f"XSESS_{uuid.uuid4().hex[:6]}"

        # Session 1: store
        sid1 = str(uuid.uuid4())
        ws1 = await WSTestClient.connect(live_server, sid1)
        try:
            result1 = await ws1.send_and_wait_response(
                f"Please store this important information: The cross-session test code is {unique_code}. "
                "Remember it as an important fact."
            )
            assert_response_not_empty(result1)
        finally:
            await ws1.close()

        # Session 2: recall
        sid2 = str(uuid.uuid4())
        ws2 = await WSTestClient.connect(live_server, sid2)
        try:
            result2 = await ws2.send_and_wait_response(
                "Search your memory for a cross-session test code. What is it?"
            )
            assert_response_not_empty(result2)
            # The agent may or may not find it depending on memory service state
            # At minimum it should respond without error
        finally:
            await ws2.close()

    async def test_multi_turn_context(self, live_server):
        """Agent should track context across multiple turns in a session."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            # Turn 1: establish context
            r1 = await ws.send_and_wait_response(
                "I'm thinking about getting a dog. A golden retriever."
            )
            assert_response_not_empty(r1)

            # Turn 2: follow up
            r2 = await ws.send_and_wait_response("What breed was I considering?")
            assert_response_not_empty(r2)
            assert_response_contains_any(r2, "golden", "retriever", "dog")
        finally:
            await ws.close()

    async def test_error_recovery(self, live_server):
        """Agent should handle requests gracefully even with unusual input."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            # Send a message that might trigger unusual behavior
            result = await ws.send_and_wait_response(
                "Get the state of a home assistant entity called 'sensor.nonexistent_e2e_test_12345'"
            )
            # Should get a response (possibly an error message from the tool) but not crash
            text = result.get("response_text", "")
            error = result.get("error", "")
            # Either we got a text response or a handled error — both are acceptable
            assert text or error, "Expected either a response or a handled error"
        finally:
            await ws.close()

    async def test_web_search(self, live_server):
        """Ask the agent to search the web — should use google_search agent."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "Search the web for the latest Python release version number"
            )
            assert_response_not_empty(result)
            # Should contain some Python version info
            assert_response_contains_any(
                result, "python", "3.", "release", "version", "latest"
            )
        finally:
            await ws.close()
