"""Idle watchdog for session workers.

Tracks the last request timestamp and triggers a graceful shutdown
when no requests have been received for the configured timeout period.
"""

import asyncio
import logging
import signal
import time
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)


class IdleWatchdog:
    """Tracks activity and signals shutdown after idle timeout."""

    def __init__(self, idle_timeout: int = 3600, check_interval: int = 60):
        """Initialize the watchdog.

        Args:
            idle_timeout: Seconds of inactivity before shutdown.
            check_interval: How often (seconds) to check for idleness.
        """
        self.idle_timeout = idle_timeout
        self.check_interval = check_interval
        self.last_activity = time.monotonic()
        self._task: Optional[asyncio.Task] = None

    def touch(self):
        """Record activity (called on each incoming request)."""
        self.last_activity = time.monotonic()

    @property
    def idle_seconds(self) -> float:
        """Seconds since last activity."""
        return time.monotonic() - self.last_activity

    async def start(self):
        """Start the background watchdog loop."""
        self._task = asyncio.create_task(self._watch_loop())
        logger.info(
            "Idle watchdog started (timeout=%ds, check_interval=%ds)",
            self.idle_timeout,
            self.check_interval,
        )

    async def stop(self):
        """Cancel the watchdog loop."""
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _watch_loop(self):
        """Periodically check idle time and trigger shutdown."""
        try:
            while True:
                await asyncio.sleep(self.check_interval)
                idle = self.idle_seconds
                if idle >= self.idle_timeout:
                    logger.info(
                        "Worker idle for %.0fs (timeout=%ds) — shutting down",
                        idle,
                        self.idle_timeout,
                    )
                    # Send SIGTERM to ourselves for graceful uvicorn shutdown
                    signal.raise_signal(signal.SIGTERM)
                    return
                else:
                    logger.debug(
                        "Watchdog check: idle=%.0fs, remaining=%.0fs",
                        idle,
                        self.idle_timeout - idle,
                    )
        except asyncio.CancelledError:
            logger.debug("Idle watchdog cancelled")


class IdleWatchdogMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that touches the watchdog on each request."""

    def __init__(self, app, watchdog: IdleWatchdog):
        super().__init__(app)
        self.watchdog = watchdog

    async def dispatch(self, request: Request, call_next):
        self.watchdog.touch()
        response = await call_next(request)
        return response
