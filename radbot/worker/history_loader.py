"""Shared history loader for seeding ADK sessions from the chat DB.

Used by both the web SessionRunner and the headless worker to populate
an InMemorySessionService with past conversation events.
"""

import logging
import uuid

from google.adk.events import Event
from google.genai.types import Content, Part

logger = logging.getLogger(__name__)


async def load_history_into_session(
    session,
    session_id: str,
    session_service,
    agent_name: str = "beto",
    max_history: int = 15,
):
    """Load conversation history from the database into an ADK session.

    Seeds the in-memory ADK session with past events so the agent retains
    context across reconnects and page refreshes.

    Args:
        session: The ADK session object to populate.
        session_id: The chat session ID (used to query the DB).
        session_service: The ADK session service (for append_event).
        agent_name: Name of the root agent (used as author on model events).
        max_history: Maximum number of messages to load from DB.
    """
    try:
        from radbot.web.db import chat_operations

        db_messages = chat_operations.get_messages_by_session_id(
            session_id, limit=max_history * 2
        )
        if not db_messages:
            logger.debug("No DB history found for session %s", session_id)
            return

        recent = db_messages[-max_history:]

        loaded = 0
        current_invocation_id = str(uuid.uuid4())
        for msg in recent:
            role = msg.get("role", "")
            content_text = msg.get("content", "")
            if not content_text:
                continue

            if role == "user":
                current_invocation_id = str(uuid.uuid4())
                event = Event(
                    invocation_id=current_invocation_id,
                    author="user",
                    content=Content(parts=[Part(text=content_text)], role="user"),
                )
            elif role == "assistant":
                event = Event(
                    invocation_id=current_invocation_id,
                    author=agent_name,
                    content=Content(parts=[Part(text=content_text)], role="model"),
                )
            else:
                continue

            await session_service.append_event(session, event)
            loaded += 1

        if loaded:
            logger.debug(
                "Loaded %d events from DB into ADK session %s", loaded, session_id
            )
    except Exception as e:
        logger.warning(
            "Failed to load history from DB into session: %s", e, exc_info=True
        )
