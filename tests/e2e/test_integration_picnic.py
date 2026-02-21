"""Picnic grocery integration e2e tests.

Read-only tests via agent chat. Auto-skipped if Picnic credentials unavailable.
"""

import uuid

import pytest

from tests.e2e.helpers.assertions import assert_response_contains_any, assert_response_not_empty
from tests.e2e.helpers.ws_client import WSTestClient

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.slow,
    pytest.mark.requires_picnic,
    pytest.mark.timeout(120),
]


class TestPicnicIntegration:
    async def test_search_product(self, live_server):
        """Search for a product on Picnic."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response("Search for milk on Picnic")
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result, "milk", "product", "picnic", "item", "result"
            )
        finally:
            await ws.close()
