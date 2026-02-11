"""
Session management package for RadBot web interface.

This package manages sessions for the RadBot web interface.
It creates and manages ADK Runner instances with the root agent.
"""

from radbot.web.api.session.dependencies import get_or_create_runner_for_session
from radbot.web.api.session.memory_api import MemoryStoreRequest, memory_router
from radbot.web.api.session.session_manager import SessionManager, get_session_manager
from radbot.web.api.session.session_runner import SessionRunner

# Export all key components
__all__ = [
    "SessionRunner",
    "SessionManager",
    "get_session_manager",
    "get_or_create_runner_for_session",
    "memory_router",
    "MemoryStoreRequest",
]
