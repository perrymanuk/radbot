"""Generic ntfy SSE subscriber service.

Connects to one or more ntfy topics via Server-Sent Events and dispatches
incoming messages to registered handler functions.  Designed as a universal
event bus — alertmanager is the first handler, but any integration can
register a handler for a topic.

Lifecycle: call ``start_ntfy_subscriber()`` during app startup.
The subscriber reads its config from the same ``integrations.ntfy`` section
as the publisher (``ntfy_client.py``), plus an additional
``subscribe_topics`` list field.
"""

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# Type for handler functions: async def handler(message: dict) -> None
HandlerFunc = Callable[[Dict[str, Any]], Awaitable[None]]

_subscriber: Optional["NtfySubscriber"] = None


class NtfySubscriber:
    """Subscribe to ntfy topics via SSE and route messages to handlers."""

    RECONNECT_DELAY = 5  # seconds between reconnect attempts

    def __init__(self, base_url: str, token: str = ""):
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._topic_handlers: Dict[str, List[HandlerFunc]] = {}
        self._tasks: List[asyncio.Task] = []
        self._running = False

    def register_handler(self, topic: str, handler: HandlerFunc) -> None:
        """Register an async handler for messages on a topic.

        Multiple handlers can be registered for the same topic.
        Handlers receive the full ntfy message dict::

            {
                "id": "abc123",
                "time": 1234567890,
                "event": "message",
                "topic": "alerts",
                "title": "...",
                "message": "...",
                "tags": ["warning"],
                "priority": 3,
            }
        """
        self._topic_handlers.setdefault(topic, []).append(handler)
        logger.info(
            f"ntfy subscriber: registered handler for topic '{topic}' "
            f"({len(self._topic_handlers[topic])} handlers)"
        )

    async def start(self) -> None:
        """Start SSE listeners for all registered topics."""
        if not self._topic_handlers:
            logger.info("ntfy subscriber: no topics registered, not starting")
            return
        self._running = True
        # One SSE connection can subscribe to multiple topics via comma-separated path
        topics = ",".join(self._topic_handlers.keys())
        task = asyncio.create_task(self._listen_loop(topics))
        self._tasks.append(task)
        logger.info(f"ntfy subscriber: started listening on topics: {topics}")

    async def stop(self) -> None:
        """Stop all listeners."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        logger.info("ntfy subscriber: stopped")

    async def _listen_loop(self, topics: str) -> None:
        """Reconnecting SSE listener loop."""
        url = f"{self._base_url}/{topics}/sse"
        headers: Dict[str, str] = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        while self._running:
            try:
                logger.debug(f"ntfy subscriber: connecting to {url}")
                async with httpx.AsyncClient(timeout=httpx.Timeout(None)) as client:
                    async with client.stream("GET", url, headers=headers) as resp:
                        resp.raise_for_status()
                        logger.info(f"ntfy subscriber: connected to {url}")
                        async for line in resp.aiter_lines():
                            if not self._running:
                                break
                            if not line:
                                continue
                            await self._handle_sse_line(line)
            except asyncio.CancelledError:
                logger.debug("ntfy subscriber: task cancelled")
                break
            except Exception as e:
                if self._running:
                    logger.warning(
                        f"ntfy subscriber: connection lost ({e}), "
                        f"reconnecting in {self.RECONNECT_DELAY}s"
                    )
                    await asyncio.sleep(self.RECONNECT_DELAY)

    async def _handle_sse_line(self, line: str) -> None:
        """Parse a line from the ntfy SSE stream and dispatch to handlers.

        ntfy sends raw JSON lines (not standard SSE ``data:`` prefix).
        Each line is a complete JSON object like:
        ``{"id":"...","event":"message","topic":"...","message":"..."}``
        """
        raw = line.strip()
        if not raw:
            return

        # Handle standard SSE data: prefix (some ntfy versions may use it)
        if raw.startswith("data:"):
            raw = raw[5:].strip()
        # Skip SSE control lines (event:, id:, retry:)
        if raw.startswith(("event:", "id:", "retry:", ":")):
            return

        if not raw:
            return

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.debug(f"ntfy subscriber: skipping non-JSON line: {raw[:100]}")
            return

        # Only process actual messages (not keepalive, open events)
        event_type = data.get("event", "")
        if event_type != "message":
            return

        topic = data.get("topic", "")
        logger.info(
            f"ntfy subscriber: received message on topic '{topic}': "
            f"{data.get('title', '(no title)')}"
        )

        await self._dispatch(data)

    async def _dispatch(self, message: Dict[str, Any]) -> None:
        """Route message to all registered handlers for its topic."""
        topic = message.get("topic", "")
        handlers = self._topic_handlers.get(topic, [])
        if not handlers:
            logger.debug(f"ntfy subscriber: no handlers for topic '{topic}'")
            return

        for handler in handlers:
            try:
                await handler(message)
            except Exception as e:
                logger.error(
                    f"ntfy subscriber: handler error for topic '{topic}': {e}",
                    exc_info=True,
                )


def _get_subscriber_config() -> dict:
    """Get subscriber config from the ntfy integration section."""
    try:
        from radbot.config.config_loader import config_loader

        cfg = config_loader.get_integrations_config().get("ntfy", {})
    except Exception:
        cfg = {}

    import os

    return {
        "url": cfg.get("url") or os.environ.get("NTFY_URL") or "https://ntfy.sh",
        "token": cfg.get("token") or os.environ.get("NTFY_TOKEN") or "",
        "subscribe_topics": cfg.get("subscribe_topics") or [],
        "enabled": cfg.get("enabled", True),
    }


async def start_ntfy_subscriber() -> Optional[NtfySubscriber]:
    """Initialize and start the ntfy subscriber if configured.

    Called during app startup or after config changes. Stops any
    existing subscriber before starting a new one.
    """
    global _subscriber

    # Stop existing subscriber if running (hot-reload)
    if _subscriber:
        await _subscriber.stop()
        _subscriber = None

    cfg = _get_subscriber_config()

    if not cfg["enabled"]:
        logger.info("ntfy subscriber: disabled in config")
        return None

    topics = cfg["subscribe_topics"]
    if not topics:
        logger.info(
            "ntfy subscriber: no subscribe_topics configured, not starting. "
            "Set integrations.ntfy.subscribe_topics to enable."
        )
        return None

    # Try credential store for token if not in config
    token = cfg["token"]
    if not token:
        try:
            from radbot.credentials.store import get_credential_store

            store = get_credential_store()
            if store.available:
                token = store.get("ntfy_token") or ""
        except Exception:
            pass

    _subscriber = NtfySubscriber(base_url=cfg["url"], token=token)

    # Register alertmanager handler for all configured topics
    try:
        from radbot.tools.alertmanager.ntfy_handler import handle_alertmanager_message

        for topic in topics:
            _subscriber.register_handler(topic, handle_alertmanager_message)
    except Exception as e:
        logger.warning(f"ntfy subscriber: failed to register alertmanager handler: {e}")

    await _subscriber.start()
    return _subscriber


async def stop_ntfy_subscriber() -> None:
    """Stop the ntfy subscriber if running."""
    global _subscriber
    if _subscriber:
        await _subscriber.stop()
        _subscriber = None


def get_ntfy_subscriber() -> Optional[NtfySubscriber]:
    """Return the active subscriber instance, or None."""
    return _subscriber


def reset_ntfy_subscriber() -> None:
    """Clear the subscriber singleton (for hot-reload)."""
    global _subscriber
    _subscriber = None
    logger.info("ntfy subscriber singleton reset")
