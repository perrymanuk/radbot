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
                result, "event", "calendar", "no event", "schedule", "nothing", "free"
            )
        finally:
            await ws.close()
