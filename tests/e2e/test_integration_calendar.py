"""Google Calendar integration e2e tests.

Read-only tests via agent chat. Auto-skipped if Calendar credentials unavailable.
"""

import uuid

import pytest

from tests.e2e.helpers.assertions import assert_response_contains_any, assert_response_not_empty
from tests.e2e.helpers.ws_client import WSTestClient

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.slow,
    pytest.mark.requires_calendar,
    pytest.mark.timeout(120),
]


class TestCalendarIntegration:
    async def test_list_calendar_events(self, live_server):
        """Ask about calendar events this week."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "What events are on my calendar this week?"
            )
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result, "event", "calendar", "no event", "schedule", "nothing", "free",
                "week", "agenda", "planner", "nada", "chillin",
            )
        finally:
            await ws.close()

    async def test_check_availability(self, live_server):
        """Ask about calendar availability."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "Am I free tomorrow afternoon? Check my calendar availability."
            )
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result, "free", "busy", "available", "calendar", "event",
                "tomorrow", "afternoon", "schedule",
            )
        finally:
            await ws.close()

    @pytest.mark.writes_external
    async def test_create_and_delete_calendar_event(self, live_server):
        """Create a calendar event then delete it (requires --run-writes)."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            # Create
            result = await ws.send_and_wait_response(
                "Create a calendar event called 'E2E Test Event' tomorrow at 11pm for 15 minutes"
            )
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result, "created", "event", "calendar", "e2e test", "scheduled"
            )

            # Delete
            result2 = await ws.send_and_wait_response(
                "Delete the 'E2E Test Event' calendar event you just created"
            )
            assert_response_not_empty(result2)
        finally:
            await ws.close()

    async def test_search_calendar_events(self, live_server):
        """Search for specific calendar events by keyword."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "Show any calendar events with 'meeting' in the title this week"
            )
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result, "event", "meeting", "calendar", "no", "found",
                "schedule", "week", "nothing",
            )
        finally:
            await ws.close()
