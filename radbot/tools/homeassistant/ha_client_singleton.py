"""
Home Assistant client singleton module.

This module provides a shared Home Assistant client instance to avoid circular imports.
"""

import logging
from typing import Optional

from radbot.config.config_loader import config_loader
from radbot.tools.homeassistant.ha_rest_client import HomeAssistantRESTClient

# Set up logging
logger = logging.getLogger(__name__)

# Singleton client instance
_ha_client = None


def reset_ha_client() -> None:
    """Reset the singleton so the next ``get_ha_client()`` re-reads config."""
    global _ha_client
    _ha_client = None


def get_ha_client() -> Optional[HomeAssistantRESTClient]:
    """
    Get or initialize the Home Assistant client.

    Reads HA config from (in order of priority):
    1. Merged config (config.yaml + DB overrides via load_db_config)
    2. Credential store (``ha_token`` entry stored by admin UI)

    Returns:
        The Home Assistant client instance, or None if configuration is invalid.
    """
    global _ha_client

    if _ha_client is not None:
        return _ha_client

    # Get configuration from merged config (file + DB overrides)
    ha_config = config_loader.get_home_assistant_config()

    # Get connection parameters from configuration
    ha_url = ha_config.get("url")
    ha_token = ha_config.get("token")

    # Check credential store for token (admin UI stores it separately as 'ha_token')
    if not ha_token:
        try:
            from radbot.credentials.store import get_credential_store

            store = get_credential_store()
            if store.available:
                ha_token = store.get("ha_token") or ""
        except Exception as e:
            logger.debug(f"Could not check credential store for ha_token: {e}")

    if not ha_url or not ha_token:
        logger.warning(
            "Home Assistant URL or token not found in config or credential store."
        )
        return None

    try:
        _ha_client = HomeAssistantRESTClient(ha_url, ha_token)

        # Test connection
        if not _ha_client.get_api_status():
            logger.error("Failed to connect to Home Assistant API.")
            _ha_client = None
        else:
            logger.info(f"Successfully connected to Home Assistant API at {ha_url}.")

        return _ha_client
    except Exception as e:
        logger.error(f"Error initializing Home Assistant client: {e}")
        _ha_client = None
        return None
