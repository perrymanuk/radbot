"""
Lazy-initialized singleton Overseerr HTTP client.

Reads config from ``integrations.overseerr`` (merged file+DB config) first,
then falls back to the credential store (``overseerr_api_key``).

Returns None when unconfigured so tools can degrade gracefully.
"""

import logging
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

# Overseerr media-request status constants
PENDING = 1
APPROVED = 2
DECLINED = 3
AVAILABLE = 5

_client: Optional["OverseerrClient"] = None
_initialized = False


def _get_config() -> dict:
    """Pull Overseerr settings from DB config, then credential store."""
    try:
        from radbot.config.config_loader import config_loader

        cfg = config_loader.get_integrations_config().get("overseerr", {})
    except Exception:
        cfg = {}

    url = cfg.get("url")
    api_key = cfg.get("api_key")
    enabled = cfg.get("enabled", True)

    # Try credential store for API key if not found above
    if not api_key:
        try:
            from radbot.credentials.store import get_credential_store

            store = get_credential_store()
            if store.available:
                api_key = store.get("overseerr_api_key")
                if api_key:
                    logger.info("Overseerr: Using API key from credential store")
        except Exception as e:
            logger.debug(f"Overseerr credential store lookup failed: {e}")

    return {
        "url": url,
        "api_key": api_key,
        "enabled": enabled,
    }


class OverseerrClient:
    """Thin wrapper around the Overseerr REST API."""

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
                "Overseerr GET %s returned %d: %s",
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
                "Overseerr POST %s returned %d: %s",
                path,
                resp.status_code,
                resp.text[:500],
            )
        resp.raise_for_status()
        return resp.json()

    # ── public API ─────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """Health-check ``GET /api/v1/status``."""
        return self._get("/api/v1/status")

    def search(self, query: str, page: int = 1) -> Dict[str, Any]:
        """Search media ``GET /api/v1/search``.

        The query is percent-encoded (spaces → ``%20``) because Overseerr
        rejects the ``+``-encoded form that ``requests`` uses by default.
        """
        encoded_query = quote(query, safe="")
        return self._get(
            f"/api/v1/search?query={encoded_query}&page={page}",
        )

    def get_movie(self, tmdb_id: int) -> Dict[str, Any]:
        """Get movie details ``GET /api/v1/movie/{id}``."""
        return self._get(f"/api/v1/movie/{tmdb_id}")

    def get_tv(self, tmdb_id: int) -> Dict[str, Any]:
        """Get TV show details ``GET /api/v1/tv/{id}``."""
        return self._get(f"/api/v1/tv/{tmdb_id}")

    def create_request(
        self,
        media_type: str,
        media_id: int,
        seasons: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """Submit a media request ``POST /api/v1/request``."""
        body: Dict[str, Any] = {
            "mediaType": media_type,
            "mediaId": media_id,
        }
        if media_type == "tv" and seasons is not None:
            body["seasons"] = seasons
        return self._post("/api/v1/request", body)

    def list_requests(
        self,
        take: int = 20,
        skip: int = 0,
        sort: str = "added",
        filter_status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List requests ``GET /api/v1/request``."""
        params: Dict[str, Any] = {"take": take, "skip": skip, "sort": sort}
        if filter_status and filter_status != "all":
            params["filter"] = filter_status
        return self._get("/api/v1/request", params=params)


def get_overseerr_client() -> Optional[OverseerrClient]:
    """Return the singleton Overseerr client, or None if unconfigured."""
    global _client, _initialized

    if _initialized:
        return _client

    _initialized = True

    cfg = _get_config()
    if not cfg["enabled"]:
        logger.info("Overseerr integration is disabled in config")
        return None

    url = cfg["url"]
    api_key = cfg["api_key"]

    if not url or not api_key:
        logger.info(
            "Overseerr integration not configured — set integrations.overseerr "
            "in config or OVERSEERR_URL/OVERSEERR_API_KEY env vars"
        )
        return None

    try:
        client = OverseerrClient(url, api_key)
        # Quick connectivity check
        status = client.get_status()
        logger.info(
            "Connected to Overseerr v%s (%s)",
            status.get("version", "?"),
            url,
        )
        _client = client
        return _client
    except Exception as e:
        logger.error("Failed to initialise Overseerr client: %s", e)
        return None


def reset_overseerr_client() -> None:
    """Clear the singleton so the next call re-initializes with fresh config."""
    global _client, _initialized
    _client = None
    _initialized = False
    logger.info("Overseerr client singleton reset")
