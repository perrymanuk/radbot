"""
Session manager for RadBot web interface.

This module provides the SessionManager class for managing multiple sessions.
"""

import asyncio
import logging
from typing import Dict, Optional

from radbot.web.api.session.session_runner import SessionRunner

# Set up logging
logger = logging.getLogger(__name__)


class SessionManager:
    """Manager for web sessions and their associated runners."""

    def __init__(self):
        """Initialize session manager."""
        self.sessions: Dict[str, SessionRunner] = {}
        self.lock = asyncio.Lock()
        logger.info("Session manager initialized")

    async def get_runner(self, session_id: str) -> Optional[SessionRunner]:
        """Get runner for a session."""
        async with self.lock:
            return self.sessions.get(session_id)

    async def set_runner(self, session_id: str, runner: SessionRunner):
        """Set runner for a session."""
        async with self.lock:
            self.sessions[session_id] = runner
            logger.info(f"Runner set for session {session_id}")

    async def reset_session(self, session_id: str):
        """Reset a session."""
        runner = await self.get_runner(session_id)
        if runner:
            runner.reset_session()
            logger.info(f"Reset session {session_id}")
        else:
            logger.warning(f"Attempted to reset non-existent session {session_id}")

    async def remove_session(self, session_id: str):
        """Remove a session."""
        async with self.lock:
            if session_id in self.sessions:
                del self.sessions[session_id]
                logger.info(f"Removed session {session_id}")
            else:
                logger.warning(f"Attempted to remove non-existent session {session_id}")


# Singleton session manager instance
_session_manager = SessionManager()


# Session manager dependency
def get_session_manager() -> SessionManager:
    """Get the session manager."""
    return _session_manager
