"""Agent routing e2e tests via WebSocket.

Tests that the agent correctly routes requests to specialized sub-agents.
"""

import uuid

import pytest

from tests.e2e.helpers.assertions import (
    assert_agent_transferred,
    assert_response_contains_any,
    assert_response_not_empty,
)
from tests.e2e.helpers.ws_client import WSTestClient

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio(loop_scope="session"), pytest.mark.slow, pytest.mark.requires_gemini, pytest.mark.timeout(120)]


class TestAgentRouting:
    async def test_route_to_tracker(self, live_server):
        """Ask about tasks — should route to tracker or use todo tools."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response("Show me my task list")
            text = assert_response_not_empty(result)
            # Should either transfer to tracker or mention tasks
            assert_response_contains_any(
                result, "task", "project", "todo", "backlog", "no task", "list"
            )
        finally:
            await ws.close()

    async def test_route_to_planner(self, live_server):
        """Ask about calendar — should route to planner."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "What events are on my calendar today?"
            )
            text = assert_response_not_empty(result)
            # Should mention calendar-related content
            assert_response_contains_any(
                result,
                "calendar", "event", "schedule", "no event",
                "today", "appointment", "nothing",
            )
        finally:
            await ws.close()

    async def test_session_reset(self, live_server):
        """Sending 'reset to beto' should trigger a reset status."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            # Send reset command
            await ws.send_raw({"message": "reset to beto"})

            # Collect messages until we see ready
            saw_reset = False
            for _ in range(10):
                msg = await ws._recv(timeout=15.0)
                if msg.get("type") == "status" and msg.get("content") == "reset":
                    saw_reset = True
                if msg.get("type") == "status" and msg.get("content") == "ready":
                    break

            assert saw_reset, "Expected 'reset' status after 'reset to beto'"
        finally:
            await ws.close()
