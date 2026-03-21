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

    async def test_route_to_casa(self, live_server, ha_available):
        """Ask about smart home — should route to casa."""
        if not ha_available:
            pytest.skip("Home Assistant not available")
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "What smart home devices do I have in Home Assistant?"
            )
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result, "device", "entity", "light", "sensor", "switch",
                "home assistant", "smart home",
            )
        finally:
            await ws.close()

    async def test_route_to_comms(self, live_server, gmail_available):
        """Ask about emails — should route to comms."""
        if not gmail_available:
            pytest.skip("Gmail not available")
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response("Show my recent emails")
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result, "email", "inbox", "message", "mail", "subject", "from"
            )
        finally:
            await ws.close()

    async def test_route_to_scout(self, live_server):
        """Ask for research — should route to scout."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "Research the differences between async and sync programming in Python. "
                "Give me a brief summary."
            )
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result, "async", "sync", "python", "concurrent", "await", "event loop"
            )
        finally:
            await ws.close()

    async def test_sequential_agent_routing(self, live_server):
        """Send a tracker question then a planner question — both should route correctly."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            # First: tracker domain
            r1 = await ws.send_and_wait_response("Show me my task list")
            assert_response_not_empty(r1)
            assert_response_contains_any(r1, "task", "project", "todo", "no task", "list")

            # Second: planner domain
            r2 = await ws.send_and_wait_response("What time is it right now?")
            assert_response_not_empty(r2)
            has_time = any(
                ind in r2["response_text"].lower()
                for ind in [":", "am", "pm", "o'clock", "hour"]
            ) or any(c.isdigit() for c in r2["response_text"])
            assert has_time, "Second response should contain time info"
        finally:
            await ws.close()
