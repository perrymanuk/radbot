"""
Session manager for RadBot web interface.

This module provides the SessionManager class for managing multiple sessions.
Supports two modes:
  - "local": Sessions run in-process via SessionRunner (default)
  - "remote": Sessions run as Nomad batch jobs, proxied via SessionProxy
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Dict, Optional, Union

from radbot.web.api.session.session_runner import SessionRunner

if TYPE_CHECKING:
    from radbot.web.api.session.session_proxy import SessionProxy

# Set up logging
logger = logging.getLogger(__name__)


def _get_session_mode() -> str:
    """Read session_mode from config. Returns 'local' or 'remote'."""
    try:
        from radbot.config.config_loader import config_loader

        agent_config = config_loader.config.get("agent", {})
        mode = agent_config.get("session_mode", "local")
        if mode in ("local", "remote"):
            return mode
        logger.warning("Unknown session_mode '%s', defaulting to 'local'", mode)
    except Exception:
        pass
    return "local"


class SessionManager:
    """Manager for web sessions and their associated runners.

    In 'local' mode, sessions are served by in-process SessionRunner instances.
    In 'remote' mode, sessions are delegated to Nomad worker jobs via SessionProxy.
    """

    def __init__(self):
        """Initialize session manager."""
        self.sessions: Dict[str, Union[SessionRunner, "SessionProxy"]] = {}
        self.lock = asyncio.Lock()
        self._mode: Optional[str] = None
        logger.info("Session manager initialized")

    @property
    def mode(self) -> str:
        """Current session mode (lazy-loaded from config)."""
        if self._mode is None:
            self._mode = _get_session_mode()
            logger.info("Session mode: %s", self._mode)
        return self._mode

    async def get_runner(
        self, session_id: str
    ) -> Optional[Union[SessionRunner, "SessionProxy"]]:
        """Get runner/proxy for a session."""
        async with self.lock:
            return self.sessions.get(session_id)

    async def set_runner(
        self, session_id: str, runner: Union[SessionRunner, "SessionProxy"]
    ):
        """Set runner/proxy for a session."""
        async with self.lock:
            self.sessions[session_id] = runner
            logger.info("Runner set for session %s (mode=%s)", session_id, self.mode)

    async def reset_session(self, session_id: str):
        """Reset a session."""
        runner = await self.get_runner(session_id)
        if runner:
            if hasattr(runner, "reset_session"):
                runner.reset_session()
            logger.info("Reset session %s", session_id)
        else:
            logger.warning("Attempted to reset non-existent session %s", session_id)

    async def remove_session(self, session_id: str):
        """Remove a session."""
        async with self.lock:
            if session_id in self.sessions:
                del self.sessions[session_id]
                logger.info("Removed session %s", session_id)
            else:
                logger.warning(
                    "Attempted to remove non-existent session %s", session_id
                )


# Singleton session manager instance
_session_manager = SessionManager()


# Session manager dependency
def get_session_manager() -> SessionManager:
    """Get the session manager."""
    return _session_manager
