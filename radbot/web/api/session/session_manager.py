"""
Session manager for RadBot web interface.

Chat sessions always run in-process via SessionRunner.  The ``session_mode``
config setting only controls terminal/workspace workers (Nomad jobs).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional

from radbot.web.api.session.session_runner import SessionRunner

# Set up logging
logger = logging.getLogger(__name__)


class SessionManager:
    """Manager for web chat sessions and their associated runners.

    Chat sessions always use in-process SessionRunner instances.
    Remote Nomad workers are only used for terminal/workspace sessions
    (managed separately by the terminal API).
    """

    def __init__(self):
        """Initialize session manager."""
        self.sessions: Dict[str, SessionRunner] = {}
        self.lock = asyncio.Lock()
        self._message_locks: Dict[str, asyncio.Lock] = {}
        logger.info("Session manager initialized")

    async def get_or_create_runner(
        self, session_id: str, user_id: str = "web_user",
        agent_name: Optional[str] = None,
    ) -> SessionRunner:
        """Atomically get or create a runner for a session.

        Holds the lock across the entire check-and-create operation to prevent
        TOCTOU races when multiple WebSocket connections arrive simultaneously.

        If ``agent_name`` isn't passed explicitly, the DB is consulted — an
        existing session keeps whichever root agent it was created with.
        Brand-new sessions fall back to ``"beto"``.
        """
        async with self.lock:
            runner = self.sessions.get(session_id)
            if runner:
                return runner

            # Resolve which root agent this session uses. An existing row wins
            # over any caller-supplied name — agent_name is immutable for a
            # session's lifetime (tied to the ADK session-service partition).
            from radbot.web.db import chat_operations

            existing = chat_operations.get_session_agent_name(session_id)
            effective_agent = existing or agent_name or "beto"

            logger.info(
                "Creating new session runner for session %s (agent=%s)",
                session_id,
                effective_agent,
            )

            runner = SessionRunner(
                user_id=user_id, session_id=session_id, agent_name=effective_agent
            )
            logger.info(
                "Created SessionRunner for session %s (root=%s)",
                session_id,
                effective_agent,
            )

            # Register session in DB — pass agent_name through so a brand-new
            # session is stamped on first touch.
            try:
                chat_operations.create_or_update_session(
                    session_id=session_id,
                    name=f"Session {session_id[:8]}",
                    user_id=user_id,
                    agent_name=effective_agent,
                )
            except Exception as db_err:
                logger.warning("Failed to register session in DB: %s", db_err)

            self.sessions[session_id] = runner
            return runner

    async def get_runner(
        self, session_id: str
    ) -> Optional[SessionRunner]:
        """Get runner for a session."""
        async with self.lock:
            return self.sessions.get(session_id)

    async def set_runner(
        self, session_id: str, runner: SessionRunner
    ):
        """Set runner for a session."""
        async with self.lock:
            self.sessions[session_id] = runner
            logger.info("Runner set for session %s", session_id)

    def get_message_lock(self, session_id: str) -> asyncio.Lock:
        """Get a per-session lock for serializing message processing.

        Prevents concurrent process_message calls on the same session
        from corrupting session.events.
        """
        if session_id not in self._message_locks:
            self._message_locks[session_id] = asyncio.Lock()
        return self._message_locks[session_id]

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
                self._message_locks.pop(session_id, None)
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
