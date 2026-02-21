"""
Lazy-initialized singleton Picnic grocery delivery client.

Reads config from ``integrations.picnic`` (merged file+DB config) first,
then falls back to the credential store (``picnic_username``, ``picnic_password``),
then to PICNIC_USERNAME / PICNIC_PASSWORD environment variables.

Returns None when unconfigured so tools can degrade gracefully.
"""

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_client: Optional["PicnicClientWrapper"] = None
_initialized = False


def _get_config() -> dict:
    """Pull Picnic settings from config manager, credential store, then env."""
    try:
        from radbot.config.config_loader import config_loader

        cfg = config_loader.get_integrations_config().get("picnic", {})
    except Exception:
        cfg = {}

    username = cfg.get("username") or os.environ.get("PICNIC_USERNAME")
    password = cfg.get("password") or os.environ.get("PICNIC_PASSWORD")
    country_code = cfg.get("country_code") or os.environ.get("PICNIC_COUNTRY_CODE", "DE")
    enabled = cfg.get("enabled", True)
    default_list_project = cfg.get("default_list_project", "Groceries")

    # Try credential store for username/password if not found above
    if not username or not password:
        try:
            from radbot.credentials.store import get_credential_store

            store = get_credential_store()
            if store.available:
                if not username:
                    username = store.get("picnic_username")
                if not password:
                    password = store.get("picnic_password")
                if username and password:
                    logger.info("Picnic: Using credentials from credential store")
        except Exception as e:
            logger.debug(f"Picnic credential store lookup failed: {e}")

    return {
        "username": username,
        "password": password,
        "country_code": country_code,
        "enabled": enabled,
        "default_list_project": default_list_project,
    }


def _get_cached_auth_token() -> Optional[str]:
    """Try to retrieve a cached auth token from the credential store."""
    try:
        from radbot.credentials.store import get_credential_store

        store = get_credential_store()
        if store.available:
            return store.get("picnic_auth_token")
    except Exception:
        pass
    return None


def _cache_auth_token(token: str) -> None:
    """Cache the auth token in the credential store for reuse."""
    try:
        from radbot.credentials.store import get_credential_store

        store = get_credential_store()
        if store.available:
            store.set(
                "picnic_auth_token",
                token,
                credential_type="auth_token",
                description="Picnic API auth token (auto-cached)",
            )
            logger.debug("Picnic auth token cached in credential store")
    except Exception as e:
        logger.debug(f"Failed to cache Picnic auth token: {e}")


class PicnicClientWrapper:
    """Wrapper around python_picnic_api.PicnicAPI with additional methods.

    Adds ``set_delivery_slot`` which is missing from the library but
    available in the Picnic REST API.
    """

    def __init__(self, username: str, password: str, country_code: str = "DE"):
        from python_picnic_api2 import PicnicAPI

        # Try cached auth token first to avoid re-login
        cached_token = _get_cached_auth_token()
        if cached_token:
            try:
                self._api = PicnicAPI(
                    auth_token=cached_token,
                    country_code=country_code,
                )
                # Verify the token still works
                self._api.get_cart()
                logger.info("Picnic: Using cached auth token")
                return
            except Exception:
                logger.debug("Picnic: Cached auth token expired, re-authenticating")

        # Fresh login
        self._api = PicnicAPI(
            username=username,
            password=password,
            country_code=country_code,
        )
        # Cache the new auth token
        if hasattr(self._api, "session") and hasattr(self._api.session, "auth_token"):
            _cache_auth_token(self._api.session.auth_token)

    # ── Delegated methods ──────────────────────────────────────

    def search(self, query: str) -> List[Dict[str, Any]]:
        """Search the Picnic product catalog."""
        return self._api.search(query)

    def get_cart(self) -> Dict[str, Any]:
        """Get the current cart contents."""
        return self._api.get_cart()

    def add_product(self, product_id: str, count: int = 1) -> Dict[str, Any]:
        """Add a product to the cart."""
        return self._api.add_product(product_id, count=count)

    def remove_product(self, product_id: str, count: int = 1) -> Dict[str, Any]:
        """Remove a product from the cart."""
        return self._api.remove_product(product_id, count=count)

    def clear_cart(self) -> Dict[str, Any]:
        """Clear all items from the cart."""
        return self._api.clear_cart()

    def get_delivery_slots(self) -> List[Dict[str, Any]]:
        """Get available delivery time slots."""
        return self._api.get_delivery_slots()

    def get_current_deliveries(self) -> List[Dict[str, Any]]:
        """Get current/upcoming deliveries."""
        return self._api.get_current_deliveries()

    def get_deliveries(self, summary: bool = True) -> List[Dict[str, Any]]:
        """Get past delivery summaries."""
        return self._api._post("/deliveries/summary", data=[])

    def get_delivery(self, delivery_id: str) -> Dict[str, Any]:
        """Get full details for a specific delivery."""
        return self._api._get(f"/deliveries/{delivery_id}")

    # ── Custom methods (not in python-picnic-api2) ────────────

    def get_lists(self) -> List[Dict[str, Any]]:
        """Get all user lists (favorites, last ordered, etc.).

        This endpoint exists in the Picnic REST API but was dropped
        from python-picnic-api2.  We call it directly.
        """
        return self._api._get("/lists")

    def get_list(self, list_id: str) -> Dict[str, Any]:
        """Get a specific user list by ID."""
        return self._api._get(f"/lists/{list_id}")

    def set_delivery_slot(self, slot_id: str) -> Dict[str, Any]:
        """Select a delivery slot and place the order.

        This method is not available in python-picnic-api2 but is
        supported by the Picnic REST API.  We call it directly using
        the underlying session.
        """
        return self._api._post("/cart/set_delivery_slot", {"slot_id": slot_id})


def get_picnic_client() -> Optional[PicnicClientWrapper]:
    """Return the singleton Picnic client, or None if unconfigured."""
    global _client, _initialized

    if _initialized:
        return _client

    cfg = _get_config()
    if not cfg["enabled"]:
        logger.info("Picnic integration is disabled in config")
        _initialized = True
        return None

    username = cfg["username"]
    password = cfg["password"]

    if not username or not password:
        logger.info(
            "Picnic integration not configured — set integrations.picnic "
            "in config or PICNIC_USERNAME/PICNIC_PASSWORD env vars"
        )
        _initialized = True
        return None

    try:
        client = PicnicClientWrapper(
            username=username,
            password=password,
            country_code=cfg["country_code"],
        )
        # Quick connectivity check
        client.get_cart()
        logger.info("Connected to Picnic (%s)", cfg["country_code"])
        _client = client
        _initialized = True
        return _client
    except Exception as e:
        logger.error("Failed to initialise Picnic client: %s", e)
        return None


def reset_picnic_client() -> None:
    """Clear the singleton so the next call re-initializes with fresh config."""
    global _client, _initialized
    _client = None
    _initialized = False
    logger.info("Picnic client singleton reset")
