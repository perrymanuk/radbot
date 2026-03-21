"""Reminders e2e tests via agent chat."""

import uuid

import pytest

from tests.e2e.helpers.assertions import (
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


class TestRemindersAgent:
    async def test_agent_create_reminder(self, live_server):
        """Ask the agent to create a reminder."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "Remind me in 24 hours to check the e2e test results"
            )
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result, "reminder", "remind", "set", "created", "will remind",
                "scheduled", "noted", "got it",
            )
        finally:
            await ws.close()

    async def test_agent_list_reminders(self, live_server):
        """Ask the agent to list reminders."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response("Show my pending reminders")
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result, "reminder", "pending", "no reminder", "none", "list", "upcoming"
            )
        finally:
            await ws.close()
