"""
Home Assistant tools package.

This package provides the functionality for interacting with Home Assistant.
"""

from radbot.tools.homeassistant.ha_client_singleton import get_ha_client
from radbot.tools.homeassistant.ha_rest_client import HomeAssistantRESTClient
from radbot.tools.homeassistant.ha_state_cache import search_ha_entities
from radbot.tools.homeassistant.ha_tools_impl import (
    get_ha_entity_state,
    list_ha_entities,
    toggle_ha_entity,
    turn_off_ha_entity,
    turn_on_ha_entity,
)

__all__ = [
    "get_ha_client",
    "HomeAssistantRESTClient",
    "search_ha_entities",
    "list_ha_entities",
    "get_ha_entity_state",
    "turn_on_ha_entity",
    "turn_off_ha_entity",
    "toggle_ha_entity",
]
