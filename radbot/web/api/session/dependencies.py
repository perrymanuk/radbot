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
    """Get or create a SessionRunner (or SessionProxy) for a session.

    Delegates to SessionManager.get_or_create_runner() which holds the lock
    across the entire check-and-create operation to prevent TOCTOU races.
    """
    try:
        return await session_manager.get_or_create_runner(session_id)
    except Exception as e:
        logger.error("Error creating session runner: %s", e, exc_info=True)
        raise
