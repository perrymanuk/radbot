"""Home Assistant integration e2e tests.

Read-only tests via agent chat. Auto-skipped if HA is unreachable.
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
            assert_response_contains_any(
                result, "sensor", "entity", "entities", "home assistant"
            )
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

    async def test_ha_list_lights(self, live_server):
        """Ask to list light entities."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "List all light entities in Home Assistant"
            )
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result, "light", "entity", "entities", "lamp", "bulb", "no light"
            )
        finally:
            await ws.close()

    async def test_ha_nonexistent_entity(self, live_server):
        """Ask about a nonexistent entity — should handle gracefully."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "What is the state of sensor.nonexistent_e2e_test_entity in Home Assistant?"
            )
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result,
                "not found",
                "error",
                "doesn't exist",
                "unknown",
                "no entity",
                "couldn't find",
                "unavailable",
                "mia",
                "can't",
                "unable",
                "no",
                "sorry",
            )
        finally:
            await ws.close()

    @pytest.mark.writes_external
    async def test_ha_toggle_entity(self, live_server):
        """Toggle a Home Assistant entity (requires --run-writes)."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "Toggle the office light in Home Assistant"
            )
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result,
                "toggled",
                "turned",
                "on",
                "off",
                "light",
                "office",
                "state",
                "changed",
            )
        finally:
            await ws.close()
