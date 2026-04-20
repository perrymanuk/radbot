"""Picnic grocery integration e2e tests.

Read-only tests via agent chat. Auto-skipped if Picnic credentials unavailable.
"""

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
            assert_response_not_empty(result)
            assert_response_contains_any(
                result, "milk", "product", "picnic", "item", "result"
            )
        finally:
            await ws.close()

    async def test_get_cart(self, live_server):
        """Ask about the Picnic cart."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response("Show me my Picnic cart")
            assert_response_not_empty(result)
            assert_response_contains_any(
                result, "cart", "empty", "item", "total", "picnic", "product"
            )
        finally:
            await ws.close()

    async def test_delivery_slots(self, live_server):
        """Ask about delivery slots."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response("When can Picnic deliver?")
            assert_response_not_empty(result)
            assert_response_contains_any(
                result, "delivery", "slot", "time", "window", "available", "picnic"
            )
        finally:
            await ws.close()

    async def test_order_history(self, live_server):
        """Ask about order history."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response("Show my Picnic order history")
            assert_response_not_empty(result)
            assert_response_contains_any(
                result, "order", "history", "past", "previous", "picnic", "no order"
            )
        finally:
            await ws.close()

    async def test_search_nonexistent_product(self, live_server):
        """Search for a nonexistent product — should handle gracefully."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "Search for xyznonexistent98765 on Picnic"
            )
            assert_response_not_empty(result)
            assert_response_contains_any(
                result,
                "no result",
                "not found",
                "couldn't find",
                "no product",
                "nothing",
                "ghost",
                "nada",
                "zero",
                "can't",
                "no",
                "sorry",
            )
        finally:
            await ws.close()

    @pytest.mark.writes_external
    async def test_add_and_remove_from_cart(self, live_server):
        """Add an item to cart then remove it (requires --run-writes)."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            # Add
            r1 = await ws.send_and_wait_response("Add milk to my Picnic cart")
            assert_response_not_empty(r1)
            assert_response_contains_any(r1, "added", "cart", "milk", "picnic")

            # Remove
            r2 = await ws.send_and_wait_response("Remove the milk from my Picnic cart")
            assert_response_not_empty(r2)
        finally:
            await ws.close()
