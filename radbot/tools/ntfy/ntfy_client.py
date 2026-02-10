"""
Lazy-initialized singleton ntfy HTTP client.

Reads config from ``integrations.ntfy`` (merged file+DB config) first,
then falls back to the credential store (``ntfy_token``), then to
NTFY_URL / NTFY_TOPIC / NTFY_TOKEN environment variables.

Returns None when unconfigured so callers can degrade gracefully.
"""

import logging
import os
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

_client: Optional["NtfyClient"] = None
_initialized = False


def _get_config() -> dict:
    """Pull ntfy settings from config manager, credential store, then env."""
    try:
        from radbot.config.config_loader import config_loader
        cfg = config_loader.get_integrations_config().get("ntfy", {})
    except Exception:
        cfg = {}

    url = cfg.get("url") or os.environ.get("NTFY_URL") or "https://ntfy.sh"
    topic = cfg.get("topic") or os.environ.get("NTFY_TOPIC") or ""
    token = cfg.get("token") or os.environ.get("NTFY_TOKEN") or ""
    enabled = cfg.get("enabled", True)
    default_priority = cfg.get("default_priority", "default")
    click_base_url = cfg.get("click_base_url") or os.environ.get("NTFY_CLICK_BASE_URL") or ""

    # Try credential store for token if not found above
    if not token:
        try:
            from radbot.credentials.store import get_credential_store
            store = get_credential_store()
            if store.available:
                token = store.get("ntfy_token") or ""
                if token:
                    logger.info("ntfy: Using access token from credential store")
        except Exception as e:
            logger.debug(f"ntfy credential store lookup failed: {e}")

    return {
        "url": url,
        "topic": topic,
        "token": token,
        "enabled": enabled,
        "default_priority": default_priority,
        "click_base_url": click_base_url,
    }


class NtfyClient:
    """Async HTTP client for ntfy push notifications."""

    # Valid ntfy priority values
    PRIORITIES = {"min", "low", "default", "high", "max"}

    def __init__(
        self,
        server_url: str,
        topic: str,
        token: str = "",
        default_priority: str = "default",
        click_base_url: str = "",
    ):
        self.server_url = server_url.rstrip("/")
        self.topic = topic
        self.default_priority = default_priority if default_priority in self.PRIORITIES else "default"
        self.click_base_url = click_base_url.rstrip("/") if click_base_url else ""

        headers: Dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._headers = headers

    async def publish(
        self,
        title: str,
        message: str,
        priority: Optional[str] = None,
        tags: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Publish a notification to the configured ntfy topic.

        Args:
            title: Notification title.
            message: Notification body (truncated to 2000 chars).
            priority: ntfy priority (min/low/default/high/max).
            tags: Comma-separated emoji tags (e.g. "robot,clock").
            session_id: If provided and click_base_url is set, generates a
                click-through URL to the chat session.

        Returns:
            The ntfy API response dict on success, or None on failure.
        """
        url = f"{self.server_url}/{self.topic}"

        # Build headers for this request
        headers = dict(self._headers)
        headers["Title"] = title[:256]

        prio = priority if priority in self.PRIORITIES else self.default_priority
        headers["Priority"] = prio

        if tags:
            headers["Tags"] = tags

        if session_id and self.click_base_url:
            headers["Click"] = f"{self.click_base_url}/?session={session_id}"

        # Truncate body
        body = message[:2000] if message else "(no content)"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, content=body, headers=headers)
                if resp.status_code == 200:
                    logger.info(f"ntfy notification sent: {title[:60]}")
                    return resp.json()
                else:
                    logger.warning(
                        "ntfy publish returned %d: %s",
                        resp.status_code, resp.text[:200],
                    )
                    return None
        except Exception as e:
            logger.error(f"ntfy publish failed: {e}")
            return None

    async def test(self) -> Dict[str, Any]:
        """Send a test notification. Returns status dict."""
        result = await self.publish(
            title="RadBot Test",
            message="Push notifications are working!",
            tags="white_check_mark,robot",
        )
        if result:
            return {"status": "ok", "message": f"Test notification sent to {self.topic}"}
        return {"status": "error", "message": "Failed to send test notification"}


def get_ntfy_client() -> Optional[NtfyClient]:
    """Return the singleton ntfy client, or None if unconfigured."""
    global _client, _initialized

    if _initialized:
        return _client

    _initialized = True

    cfg = _get_config()
    if not cfg["enabled"]:
        logger.info("ntfy integration is disabled in config")
        return None

    topic = cfg["topic"]
    if not topic:
        logger.info(
            "ntfy integration not configured -- set integrations.ntfy.topic "
            "in config or NTFY_TOPIC env var"
        )
        return None

    _client = NtfyClient(
        server_url=cfg["url"],
        topic=topic,
        token=cfg["token"],
        default_priority=cfg["default_priority"],
        click_base_url=cfg["click_base_url"],
    )
    logger.info(f"ntfy client initialized (topic={topic}, server={cfg['url']})")
    return _client


def reset_ntfy_client() -> None:
    """Clear the singleton so the next call re-initializes with fresh config."""
    global _client, _initialized
    _client = None
    _initialized = False
    logger.info("ntfy client singleton reset")
