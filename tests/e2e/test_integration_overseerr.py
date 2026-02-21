"""Overseerr integration e2e tests.

Read-only tests via agent chat. Auto-skipped if Overseerr is unreachable.
"""

import uuid

import pytest

from tests.e2e.helpers.assertions import assert_response_contains_any, assert_response_not_empty
from tests.e2e.helpers.ws_client import WSTestClient

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.slow,
    pytest.mark.requires_overseerr,
    pytest.mark.timeout(120),
]


class TestOverseerrIntegration:
    async def test_search_media(self, live_server):
        """Search for a well-known movie on Overseerr."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "Search for The Matrix on Overseerr"
            )
            text = assert_response_not_empty(result)
            assert_response_contains_any(result, "matrix", "movie", "film", "media", "result")
        finally:
            await ws.close()
