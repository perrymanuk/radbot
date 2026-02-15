"""
Home Assistant WebSocket client singleton module.

Follows the same pattern as ``ha_client_singleton.py`` but for the
async WebSocket client used by dashboard tools.
"""

import logging
import os
from typing import Optional

from radbot.tools.homeassistant.ha_websocket_client import (
    HomeAssistantWebSocketClient,
    _derive_ws_url,
)

logger = logging.getLogger(__name__)

# Singleton client instance
_ws_client: Optional[HomeAssistantWebSocketClient] = None


def reset_ha_ws_client() -> None:
    """Reset the singleton so the next ``get_ha_ws_client()`` re-reads config."""
    global _ws_client
    _ws_client = None


async def get_ha_ws_client() -> Optional[HomeAssistantWebSocketClient]:
    """Get or initialise the HA WebSocket client singleton.

    Reads the same config sources as the REST client singleton:
    1. Merged config (config.yaml + DB overrides)
    2. Credential store (``ha_token``)
    3. Environment variables (``HA_URL``, ``HA_TOKEN``)

    The WebSocket URL is derived from the REST URL automatically.
    """
    global _ws_client

    if _ws_client is not None:
        return _ws_client

    # --- resolve URL + token (same logic as ha_client_singleton) ---
    from radbot.config.config_loader import config_loader

    ha_config = config_loader.get_home_assistant_config()
    ha_url = ha_config.get("url")
    ha_token = ha_config.get("token")

    if not ha_token:
        try:
            from radbot.credentials.store import get_credential_store

            store = get_credential_store()
            if store.available:
                ha_token = store.get("ha_token") or ""
        except Exception as e:
            logger.debug(f"Could not check credential store for ha_token: {e}")

    if not ha_url:
        ha_url = os.getenv("HA_URL")
    if not ha_token:
        ha_token = os.getenv("HA_TOKEN")

    if not ha_url or not ha_token:
        logger.warning(
            "Home Assistant URL or token not found — WebSocket client unavailable."
        )
        return None

    ws_url = _derive_ws_url(ha_url)

    try:
        client = HomeAssistantWebSocketClient(ws_url, ha_token)
        await client.connect()
        logger.info(f"HA WebSocket client connected to {ws_url}")
        _ws_client = client
        return _ws_client
    except Exception as e:
        logger.error(f"Failed to connect HA WebSocket client: {e}")
        return None
