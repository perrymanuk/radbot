"""Lazy-initialized singleton Ollama HTTP client for admin operations.

Reads config from ``integrations.ollama`` (merged file+DB config) first,
then falls back to the credential store (``ollama_api_key``), then to
``OLLAMA_API_BASE`` / ``OLLAMA_API_KEY`` environment variables.

Returns None when unconfigured so admin endpoints can degrade gracefully.
"""

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

_client: Optional["OllamaClient"] = None
_initialized = False


def _get_config() -> dict:
    """Pull Ollama settings from config manager, credential store, then env."""
    try:
        from radbot.config.config_loader import config_loader

        cfg = config_loader.get_integrations_config().get("ollama", {})
    except Exception:
        cfg = {}

    api_base = cfg.get("api_base") or os.environ.get("OLLAMA_API_BASE")
    api_key = cfg.get("api_key") or os.environ.get("OLLAMA_API_KEY")
    enabled = cfg.get("enabled", True)

    # Try credential store for API key if not found above
    if not api_key:
        try:
            from radbot.credentials.store import get_credential_store

            store = get_credential_store()
            if store.available:
                api_key = store.get("ollama_api_key")
                if api_key:
                    logger.info("Ollama: Using API key from credential store")
        except Exception as e:
            logger.debug(f"Ollama credential store lookup failed: {e}")

    return {
        "api_base": api_base,
        "api_key": api_key,
        "enabled": enabled,
    }


class OllamaClient:
    """Thin wrapper around the Ollama REST API for admin operations."""

    def __init__(self, base_url: str, api_key: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        headers: Dict[str, str] = {"Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.Client(headers=headers, timeout=30.0)

    def close(self) -> None:
        self._client.close()

    # ── helpers ────────────────────────────────────────────────

    def _get(self, path: str) -> Any:
        resp = self._client.get(f"{self.base_url}{path}")
        if not resp.is_success:
            logger.error(
                "Ollama GET %s returned %d: %s",
                path,
                resp.status_code,
                resp.text[:500],
            )
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, json_body: Optional[dict] = None, timeout: float = 30.0) -> Any:
        resp = self._client.post(
            f"{self.base_url}{path}",
            json=json_body,
            timeout=timeout,
        )
        if not resp.is_success:
            logger.error(
                "Ollama POST %s returned %d: %s",
                path,
                resp.status_code,
                resp.text[:500],
            )
        resp.raise_for_status()
        return resp.json()

    def _delete(self, path: str, json_body: Optional[dict] = None) -> Any:
        resp = self._client.request(
            "DELETE",
            f"{self.base_url}{path}",
            json=json_body,
        )
        if not resp.is_success:
            logger.error(
                "Ollama DELETE %s returned %d: %s",
                path,
                resp.status_code,
                resp.text[:500],
            )
        resp.raise_for_status()
        return resp.json() if resp.text else {"status": "ok"}

    # ── public API ─────────────────────────────────────────────

    def get_version(self) -> Dict[str, Any]:
        """Health-check ``GET /api/version``."""
        return self._get("/api/version")

    def list_models(self) -> List[Dict[str, Any]]:
        """List downloaded models ``GET /api/tags``."""
        data = self._get("/api/tags")
        return data.get("models", [])

    def show_model(self, model_name: str) -> Dict[str, Any]:
        """Get model details ``POST /api/show``."""
        return self._post("/api/show", {"name": model_name})

    def pull_model(self, model_name: str) -> Dict[str, Any]:
        """Pull a model ``POST /api/pull`` (blocking, 600s timeout for large models)."""
        return self._post(
            "/api/pull",
            {"name": model_name, "stream": False},
            timeout=600.0,
        )

    def delete_model(self, model_name: str) -> Dict[str, Any]:
        """Delete a model ``DELETE /api/delete``."""
        return self._delete("/api/delete", {"name": model_name})


def get_ollama_client() -> Optional[OllamaClient]:
    """Return the singleton Ollama client, or None if unconfigured."""
    global _client, _initialized

    if _initialized:
        return _client

    _initialized = True

    cfg = _get_config()
    if not cfg["enabled"]:
        logger.info("Ollama integration is disabled in config")
        return None

    api_base = cfg["api_base"]
    if not api_base:
        logger.info(
            "Ollama integration not configured — set integrations.ollama.api_base "
            "in config or OLLAMA_API_BASE env var"
        )
        return None

    try:
        client = OllamaClient(api_base, api_key=cfg.get("api_key"))
        version = client.get_version()
        logger.info(
            "Connected to Ollama %s (%s)",
            version.get("version", "?"),
            api_base,
        )
        _client = client
        return _client
    except Exception as e:
        logger.error("Failed to initialise Ollama client: %s", e)
        return None


def reset_ollama_client() -> None:
    """Clear the singleton so the next call re-initializes with fresh config."""
    global _client, _initialized
    if _client is not None:
        try:
            _client.close()
        except Exception:
            pass
    _client = None
    _initialized = False
    logger.info("Ollama client singleton reset")
