"""
Lazy-initialized singleton Lidarr HTTP client.

Reads config from ``integrations.lidarr`` (merged file+DB config) first,
then falls back to the credential store (``lidarr_api_key``), then to
LIDARR_URL / LIDARR_API_KEY environment variables.

Returns None when unconfigured so tools can degrade gracefully.
"""

import logging
import os
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

_client: Optional["LidarrClient"] = None
_initialized = False


def _get_config() -> dict:
    """Pull Lidarr settings from config manager, credential store, then env."""
    try:
        from radbot.config.config_loader import config_loader

        cfg = config_loader.get_integrations_config().get("lidarr", {})
    except Exception:
        cfg = {}

    url = cfg.get("url") or os.environ.get("LIDARR_URL")
    api_key = cfg.get("api_key") or os.environ.get("LIDARR_API_KEY")
    enabled = cfg.get("enabled", True)

    # Try credential store for API key if not found above
    if not api_key:
        try:
            from radbot.credentials.store import get_credential_store

            store = get_credential_store()
            if store.available:
                api_key = store.get("lidarr_api_key")
                if api_key:
                    logger.info("Lidarr: Using API key from credential store")
        except Exception as e:
            logger.debug(f"Lidarr credential store lookup failed: {e}")

    return {
        "url": url,
        "api_key": api_key,
        "enabled": enabled,
    }


class LidarrClient:
    """Thin wrapper around the Lidarr REST API (v1)."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update(
            {
                "X-Api-Key": api_key,
                "Accept": "application/json",
            }
        )

    # ── helpers ────────────────────────────────────────────────

    def _get(self, path: str, params: Optional[dict] = None) -> Any:
        resp = self._session.get(
            f"{self.base_url}{path}",
            params=params,
            timeout=15,
        )
        if not resp.ok:
            logger.error(
                "Lidarr GET %s returned %d: %s",
                path,
                resp.status_code,
                resp.text[:500],
            )
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, json_body: dict) -> Any:
        resp = self._session.post(
            f"{self.base_url}{path}",
            json=json_body,
            timeout=15,
        )
        if not resp.ok:
            logger.error(
                "Lidarr POST %s returned %d: %s",
                path,
                resp.status_code,
                resp.text[:500],
            )
        resp.raise_for_status()
        return resp.json()

    # ── public API ─────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """Health-check ``GET /api/v1/system/status``."""
        return self._get("/api/v1/system/status")

    def lookup_artist(self, term: str) -> List[Dict[str, Any]]:
        """Search for artists ``GET /api/v1/artist/lookup``."""
        encoded = quote(term, safe="")
        return self._get(f"/api/v1/artist/lookup?term={encoded}")

    def lookup_album(self, term: str) -> List[Dict[str, Any]]:
        """Search for albums ``GET /api/v1/album/lookup``."""
        encoded = quote(term, safe="")
        return self._get(f"/api/v1/album/lookup?term={encoded}")

    def get_root_folders(self) -> List[Dict[str, Any]]:
        """List root folders ``GET /api/v1/rootfolder``."""
        return self._get("/api/v1/rootfolder")

    def get_quality_profiles(self) -> List[Dict[str, Any]]:
        """List quality profiles ``GET /api/v1/qualityprofile``."""
        return self._get("/api/v1/qualityprofile")

    def get_metadata_profiles(self) -> List[Dict[str, Any]]:
        """List metadata profiles ``GET /api/v1/metadataprofile``."""
        return self._get("/api/v1/metadataprofile")

    def add_artist(self, artist_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add an artist ``POST /api/v1/artist``."""
        return self._post("/api/v1/artist", artist_data)

    def add_album(self, album_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add an album ``POST /api/v1/album``."""
        return self._post("/api/v1/album", album_data)


def get_lidarr_client() -> Optional[LidarrClient]:
    """Return the singleton Lidarr client, or None if unconfigured."""
    global _client, _initialized

    if _initialized:
        return _client

    cfg = _get_config()
    if not cfg["enabled"]:
        logger.info("Lidarr integration is disabled in config")
        _initialized = True
        return None

    url = cfg["url"]
    api_key = cfg["api_key"]

    if not url or not api_key:
        logger.info(
            "Lidarr integration not configured — set integrations.lidarr "
            "in config or LIDARR_URL/LIDARR_API_KEY env vars"
        )
        _initialized = True
        return None

    try:
        client = LidarrClient(url, api_key)
        status = client.get_status()
        logger.info(
            "Connected to Lidarr v%s (%s)",
            status.get("version", "?"),
            url,
        )
        _client = client
        _initialized = True
        return _client
    except Exception as e:
        logger.error("Failed to initialise Lidarr client: %s", e)
        return None


def reset_lidarr_client() -> None:
    """Clear the singleton so the next call re-initializes with fresh config."""
    global _client, _initialized
    _client = None
    _initialized = False
    logger.info("Lidarr client singleton reset")
