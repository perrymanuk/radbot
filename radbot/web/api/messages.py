"""
Message API endpoints for RadBot web interface.

This module provides API endpoints for storing and retrieving chat messages.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field

from radbot.web.db import chat_operations

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Pydantic models for request/response
class MessageModel(BaseModel):
    """Message model for API responses."""

    message_id: str
    session_id: str
    role: str
    content: str
    agent_name: Optional[str] = None
    timestamp: str
    user_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class MessageCreateRequest(BaseModel):
    """Request model for creating a new message."""

    role: str = Field(..., description="Message role: 'user', 'assistant', or 'system'")
    content: str = Field(..., description="Message content")
    agent_name: Optional[str] = Field(
        None, description="Agent name for assistant messages"
    )
    user_id: Optional[str] = Field(None, description="User identifier")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class MessagesResponse(BaseModel):
    """Response model for messages list."""

    messages: List[MessageModel]
    total_count: int
    has_more: bool


class BatchMessageCreateRequest(BaseModel):
    """Request model for batch creating messages."""

    messages: List[MessageCreateRequest]


# Create router function for registration
def register_messages_router(app):
    """Register messages router with the FastAPI app."""
    router = APIRouter(
        prefix="/api/messages",
        tags=["messages"],
    )

    @router.post("/{session_id}", status_code=201)
    async def create_message(
        session_id: str = Path(..., description="Session identifier"),
        request: MessageCreateRequest = None,
    ):
        """
        Create a new message.

        Args:
            session_id: Session identifier
            request: Message creation request

        Returns:
            Dict with status and message_id
        """
        logger.info(f"Creating message for session {session_id}")

        if not request:
            raise HTTPException(status_code=400, detail="Message content is required")

        # Validate role
        if request.role not in ("user", "assistant", "system"):
            raise HTTPException(
                status_code=400, detail="Role must be 'user', 'assistant', or 'system'"
            )

        # Create chat session if it doesn't exist
        chat_operations.create_or_update_session(session_id)

        try:
            message_id = chat_operations.add_message(
                session_id=session_id,
                role=request.role,
                content=request.content,
                agent_name=request.agent_name,
                user_id=request.user_id,
                metadata=request.metadata,
            )

            if not message_id:
                raise HTTPException(status_code=500, detail="Failed to create message")

            return {"status": "success", "message_id": message_id}
        except Exception as e:
            logger.error(f"Error creating message: {e}")
            raise HTTPException(
                status_code=500, detail=f"Error creating message: {str(e)}"
            )

    @router.post("/{session_id}/batch", status_code=201)
    async def create_messages_batch(
        session_id: str = Path(..., description="Session identifier"),
        request: BatchMessageCreateRequest = None,
    ):
        """
        Create multiple messages at once.

        Args:
            session_id: Session identifier
            request: Batch message creation request

        Returns:
            Dict with status and list of created message IDs
        """
        if not request or not request.messages:
            raise HTTPException(status_code=400, detail="Messages are required")

        logger.info(
            f"Batch creating {len(request.messages)} messages for session {session_id}"
        )

        # Create chat session if it doesn't exist
        chat_operations.create_or_update_session(session_id)

        try:
            message_ids = []
            for msg in request.messages:
                # Validate role
                if msg.role not in ("user", "assistant", "system"):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Role must be 'user', 'assistant', or 'system' (got '{msg.role}')",
                    )

                message_id = chat_operations.add_message(
                    session_id=session_id,
                    role=msg.role,
                    content=msg.content,
                    agent_name=msg.agent_name,
                    user_id=msg.user_id,
                    metadata=msg.metadata,
                )

                if message_id:
                    message_ids.append(message_id)

            if not message_ids:
                raise HTTPException(
                    status_code=500, detail="Failed to create any messages"
                )

            return {
                "status": "success",
                "message_ids": message_ids,
                "count": len(message_ids),
            }
        except HTTPException:
            raise  # Re-raise HTTP exceptions
        except Exception as e:
            logger.error(f"Error batch creating messages: {e}")
            raise HTTPException(
                status_code=500, detail=f"Error batch creating messages: {str(e)}"
            )

    @router.get("/{session_id}")
    async def get_messages(
        session_id: str = Path(..., description="Session identifier"),
        limit: int = Query(
            200, ge=1, le=500, description="Maximum number of messages to return"
        ),
        offset: int = Query(0, ge=0, description="Number of messages to skip"),
    ):
        """
        Get messages for a session.

        Args:
            session_id: Session identifier
            limit: Maximum number of messages to return
            offset: Number of messages to skip

        Returns:
            MessagesResponse with messages list, total count, and has_more flag
        """
        logger.info(
            f"Getting messages for session {session_id} (limit={limit}, offset={offset})"
        )

        try:
            # Get total count first (for pagination)
            total_count = chat_operations.get_session_message_count(session_id)

            # Get messages with limit+1 to check if there are more
            messages = chat_operations.get_messages_by_session_id(
                session_id=session_id,
                limit=limit + 1,  # Get one extra to check if there are more
                offset=offset,
            )

            # Check if there are more messages
            has_more = len(messages) > limit
            if has_more:
                messages = messages[:limit]  # Remove the extra message

            return MessagesResponse(
                messages=messages, total_count=total_count, has_more=has_more
            )
        except Exception as e:
            logger.error(f"Error getting messages: {e}")
            raise HTTPException(
                status_code=500, detail=f"Error getting messages: {str(e)}"
            )

    # Register the router with the app
    app.include_router(router)
    logger.info("Messages router registered")
