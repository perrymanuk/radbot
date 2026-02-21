"""Home Assistant integration e2e tests.

Read-only tests via agent chat. Auto-skipped if HA is unreachable.
"""

import uuid

import pytest

from tests.e2e.helpers.assertions import assert_response_contains_any, assert_response_not_empty
from tests.e2e.helpers.ws_client import WSTestClient

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.slow,
    pytest.mark.requires_ha,
    pytest.mark.timeout(120),
]


class TestHomeAssistantIntegration:
    async def test_ha_search_entities(self, live_server):
        """Ask to search HA entities — should list some entities."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "Search for sensor entities in Home Assistant"
            )
            text = assert_response_not_empty(result)
            assert_response_contains_any(result, "sensor", "entity", "entities", "home assistant")
        finally:
            await ws.close()

    async def test_ha_entity_state(self, live_server):
        """Ask about a specific entity state."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "What sensor entities are available in Home Assistant? Just list a few."
            )
            text = assert_response_not_empty(result)
            # Should mention something about entities or state
            assert_response_contains_any(
                result, "sensor", "entity", "state", "temperature", "humidity", "light"
            )
        finally:
            await ws.close()
