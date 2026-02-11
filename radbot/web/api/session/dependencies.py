"""
Dependencies for RadBot web interface.

This module provides FastAPI dependencies for the web interface.
"""

import logging
from typing import Optional

from fastapi import Depends

from radbot.web.api.session.session_manager import SessionManager, get_session_manager
from radbot.web.api.session.session_runner import SessionRunner

# Set up logging
logger = logging.getLogger(__name__)


# Runner dependency for FastAPI
async def get_or_create_runner_for_session(
    session_id: str, session_manager: SessionManager = Depends(get_session_manager)
) -> SessionRunner:
    """Get or create a SessionRunner for a session."""
    # Check if we already have a runner for this session
    runner = await session_manager.get_runner(session_id)
    if runner:
        logger.info(f"Using existing runner for session {session_id}")
        return runner

    # Create a new runner for this session
    logger.info(f"Creating new session runner for session {session_id}")

    try:
        # Use a fixed user_id so memories persist across all sessions
        user_id = "web_user"

        # Create new runner
        runner = SessionRunner(user_id=user_id, session_id=session_id)
        logger.info(f"Created new SessionRunner for user {user_id}")

        # Ensure session is registered in the database
        try:
            from radbot.web.db import chat_operations

            chat_operations.create_or_update_session(
                session_id=session_id,
                name=f"Session {session_id[:8]}",
                user_id=user_id,
            )
        except Exception as db_err:
            logger.warning(f"Failed to register session in DB: {db_err}")

        # Store the runner in the session manager
        await session_manager.set_runner(session_id, runner)

        return runner
    except Exception as e:
        logger.error(f"Error creating session runner: {str(e)}", exc_info=True)
        raise
