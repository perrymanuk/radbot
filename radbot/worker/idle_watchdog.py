"""Activity watchdog for session workers.

Tracks the last request timestamp for health/observability endpoints.
Workers are persistent — they do not self-terminate.
"""

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)


class ActivityWatchdog:
    """Tracks last activity time for health reporting."""

    def __init__(self):
        self.last_activity = time.monotonic()
        self._start_time = time.monotonic()

    def touch(self):
        """Record activity (called on each incoming request)."""
        self.last_activity = time.monotonic()

    @property
    def idle_seconds(self) -> float:
        """Seconds since last activity."""
        return time.monotonic() - self.last_activity

    @property
    def uptime_seconds(self) -> float:
        """Seconds since worker started."""
        return time.monotonic() - self._start_time


class ActivityMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that touches the watchdog on each request."""

    def __init__(self, app, watchdog: ActivityWatchdog):
        super().__init__(app)
        self.watchdog = watchdog

    async def dispatch(self, request: Request, call_next):
        self.watchdog.touch()
        response = await call_next(request)
        return response
