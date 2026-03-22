"""
Dependencies for RadBot web interface.

This module provides FastAPI dependencies for the web interface.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Union

from fastapi import Depends

from radbot.web.api.session.session_manager import SessionManager, get_session_manager
from radbot.web.api.session.session_runner import SessionRunner

if TYPE_CHECKING:
    from radbot.web.api.session.session_proxy import SessionProxy

# Set up logging
logger = logging.getLogger(__name__)


# Runner dependency for FastAPI
async def get_or_create_runner_for_session(
    session_id: str, session_manager: SessionManager = Depends(get_session_manager)
) -> Union[SessionRunner, "SessionProxy"]:
    """Get or create a SessionRunner (or SessionProxy) for a session."""
    # Check if we already have a runner for this session
    runner = await session_manager.get_runner(session_id)
    if runner:
        logger.info("Using existing runner for session %s", session_id)
        return runner

    # Create a new runner for this session
    logger.info(
        "Creating new session runner for session %s (mode=%s)",
        session_id,
        session_manager.mode,
    )

    try:
        # Use a fixed user_id so memories persist across all sessions
        user_id = "web_user"

        if session_manager.mode == "remote":
            from radbot.web.api.session.session_proxy import SessionProxy

            runner = SessionProxy(user_id=user_id, session_id=session_id)
            logger.info("Created SessionProxy for session %s", session_id)
        else:
            runner = SessionRunner(user_id=user_id, session_id=session_id)
            logger.info("Created SessionRunner for user %s", user_id)

        # Ensure session is registered in the database
        try:
            from radbot.web.db import chat_operations

            chat_operations.create_or_update_session(
                session_id=session_id,
                name=f"Session {session_id[:8]}",
                user_id=user_id,
            )
        except Exception as db_err:
            logger.warning("Failed to register session in DB: %s", db_err)

        # Store the runner in the session manager
        await session_manager.set_runner(session_id, runner)

        return runner
    except Exception as e:
        logger.error("Error creating session runner: %s", e, exc_info=True)
        raise
