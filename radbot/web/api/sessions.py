"""
Sessions API endpoints for RadBot web interface.

This module provides API endpoints for managing multiple chat sessions.
"""

import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel

from radbot.web.api.session import (
    SessionManager,
    get_session_manager,
)
from radbot.web.db import chat_operations
from radbot.web.db.connection import (
    CHAT_SCHEMA,
    get_chat_db_connection,
    get_chat_db_cursor,
)

logger = logging.getLogger(__name__)


# Pydantic models for request/response
class SessionMetadata(BaseModel):
    """Session metadata for API responses."""

    id: str
    name: str
    description: Optional[str] = None
    created_at: str
    last_message_at: Optional[str] = None
    preview: Optional[str] = None
    agent_name: str = "beto"


class CreateSessionRequest(BaseModel):
    """Request model for creating a new session."""

    session_id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    user_id: Optional[str] = None
    agent_name: Optional[str] = None  # "beto" (default) or "scout"


class UpdateSessionRequest(BaseModel):
    """Request model for updating a session."""

    name: Optional[str] = None
    description: Optional[str] = None


class RenameSessionRequest(BaseModel):
    """Request model for renaming a session (legacy)."""

    name: str


class SessionsListResponse(BaseModel):
    """Response model for listing sessions."""

    sessions: List[SessionMetadata]
    active_session_id: Optional[str] = None


# Register the router with FastAPI
def register_sessions_router(app):
    """Register the sessions router with the FastAPI app."""
    router = APIRouter(
        prefix="/api/sessions",
        tags=["sessions"],
    )

    @router.get("/", response_model=SessionsListResponse)
    async def list_sessions(
        user_id: Optional[str] = None,
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
        session_manager: SessionManager = Depends(get_session_manager),
    ):
        """List all sessions for the current user."""
        logger.debug("Listing sessions for user %s", user_id or "anonymous")

        # Create the response with placeholder data - in a real system
        # we would query a database for user's sessions
        sessions = []
        active_session_id = None

        try:
            # Get sessions from database
            db_sessions = chat_operations.list_sessions(
                user_id=user_id, limit=limit, offset=offset
            )

            # Transform to API model
            for db_session in db_sessions:
                session_meta = SessionMetadata(
                    id=db_session["session_id"],
                    name=db_session["name"] or f"Session {db_session['created_at']}",
                    description=db_session.get("description"),
                    created_at=db_session["created_at"],
                    last_message_at=db_session["last_message_at"],
                    preview=db_session["preview"] or "New session",
                    agent_name=db_session.get("agent_name") or "beto",
                )
                sessions.append(session_meta)

            # If there's at least one session, use the first as active
            if sessions:
                active_session_id = sessions[0].id

            logger.debug("Found %d sessions for user", len(sessions))

            return SessionsListResponse(
                sessions=sessions, active_session_id=active_session_id
            )
        except Exception as e:
            logger.error("Error listing sessions: %s", str(e), exc_info=True)
            raise HTTPException(
                status_code=500, detail=f"Error listing sessions: {str(e)}"
            )

    @router.post("/create", response_model=SessionMetadata, status_code=201)
    async def create_session(
        request: CreateSessionRequest,
        session_manager: SessionManager = Depends(get_session_manager),
    ):
        """Create a new session."""
        logger.info("Creating new session with name: %s", request.name)

        try:
            # Use provided session ID or generate a new one
            session_id = request.session_id or str(uuid.uuid4())
            user_id = "web_user"

            # Default name if not provided
            session_name = request.name or f"Session {session_id[:8]}"
            # Guard against typos / unknown agents — refuse explicitly instead
            # of silently routing to beto.
            agent_name = (request.agent_name or "beto").strip()
            if agent_name not in {"beto", "scout"}:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown agent_name '{agent_name}'. Allowed: beto, scout.",
                )

            # Insert the DB row FIRST so the runner (which reads agent_name
            # from the DB row) gets the right root agent on first touch.
            success = chat_operations.create_or_update_session(
                session_id=session_id,
                name=session_name,
                user_id=user_id,
                description=request.description,
                agent_name=agent_name,
            )

            if not success:
                raise HTTPException(
                    status_code=500, detail="Failed to create session in database"
                )

            # Now spin up the runner — it'll pick up agent_name from the row
            await session_manager.get_or_create_runner(
                session_id, user_id=user_id, agent_name=agent_name
            )

            # Get current timestamp
            import datetime

            created_at = datetime.datetime.now().isoformat()

            # Return session metadata
            return SessionMetadata(
                id=session_id,
                name=session_name,
                created_at=created_at,
                preview="New session started",
                agent_name=agent_name,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error creating session: %s", str(e), exc_info=True)
            raise HTTPException(
                status_code=500, detail=f"Error creating session: {str(e)}"
            )

    @router.put("/{session_id}/rename", response_model=SessionMetadata)
    async def update_session(
        session_id: str = Path(...),
        request: UpdateSessionRequest = None,
        session_manager: SessionManager = Depends(get_session_manager),
    ):
        """Update a session's name and/or description."""
        if not request or (not request.name and request.description is None):
            raise HTTPException(
                status_code=400, detail="Name or description is required"
            )

        logger.debug("Updating session %s", session_id)

        try:
            # Update in database — don't require runner to exist (session may be in DB only)
            success = chat_operations.create_or_update_session(
                session_id=session_id,
                name=request.name,
                description=request.description,
            )

            if not success:
                raise HTTPException(
                    status_code=500, detail="Failed to update session in database"
                )

            # Get session details
            db_sessions = chat_operations.list_sessions(limit=100)
            db_session = next(
                (s for s in db_sessions if s["session_id"] == session_id), None
            )

            if not db_session:
                raise HTTPException(
                    status_code=404,
                    detail=f"Session {session_id} not found in database",
                )

            return SessionMetadata(
                id=session_id,
                name=db_session.get("name", f"Session {session_id[:8]}"),
                description=db_session.get("description"),
                created_at=db_session["created_at"],
                last_message_at=db_session.get("last_message_at"),
                preview=db_session.get("preview", "Session updated"),
                agent_name=db_session.get("agent_name") or "beto",
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error updating session: %s", str(e), exc_info=True)
            raise HTTPException(
                status_code=500, detail=f"Error updating session: {str(e)}"
            )

    @router.delete("/{session_id}")
    async def delete_session(
        session_id: str = Path(...),
        session_manager: SessionManager = Depends(get_session_manager),
    ):
        """Delete a session."""
        logger.info("Deleting session %s", session_id)

        try:
            # Remove from session manager if it has a runner
            runner = await session_manager.get_runner(session_id)
            if runner:
                await session_manager.remove_session(session_id)

            # Mark as inactive in database
            success = chat_operations.delete_session(session_id)

            if not success:
                logger.warning(
                    "Failed to mark session %s as inactive in database", session_id
                )

            return {"status": "success", "message": f"Session {session_id} deleted"}
        except Exception as e:
            logger.error("Error deleting session: %s", str(e), exc_info=True)
            raise HTTPException(
                status_code=500, detail=f"Error deleting session: {str(e)}"
            )

    @router.get("/{session_id}")
    async def get_session(
        session_id: str = Path(...),
        session_manager: SessionManager = Depends(get_session_manager),
    ):
        """Get session details."""
        logger.debug("Getting details for session %s", session_id)

        try:
            # Check if session exists in the manager
            runner = await session_manager.get_runner(session_id)
            if not runner:
                raise HTTPException(
                    status_code=404, detail=f"Session {session_id} not found"
                )

            # Get session from database
            sessions = chat_operations.list_sessions(limit=1)
            db_session = next(
                (s for s in sessions if s["session_id"] == session_id), None
            )

            if not db_session:
                # Create session in database if it exists in manager but not in DB
                chat_operations.create_or_update_session(
                    session_id=session_id, name=f"Session {session_id[:8]}"
                )

                import datetime

                # Return basic info
                return {
                    "id": session_id,
                    "name": f"Session {session_id[:8]}",
                    "created_at": datetime.datetime.now().isoformat(),
                    "preview": "New session",
                }

            # Return session data from database
            return {
                "id": session_id,
                "name": db_session.get("name", f"Session {session_id[:8]}"),
                "created_at": db_session["created_at"],
                "last_message_at": db_session.get("last_message_at"),
                "preview": db_session.get("preview", "Session data"),
                "agent_name": db_session.get("agent_name") or "beto",
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error getting session: %s", str(e), exc_info=True)
            raise HTTPException(
                status_code=500, detail=f"Error getting session: {str(e)}"
            )

    @router.post("/{session_id}/reset")
    async def reset_session(
        session_id: str = Path(...),
        session_manager: SessionManager = Depends(get_session_manager),
    ):
        """Reset a session (clear messages but keep session)."""
        logger.info("Resetting session %s", session_id)

        try:
            # Check if session exists
            runner = await session_manager.get_runner(session_id)
            if not runner:
                raise HTTPException(
                    status_code=404, detail=f"Session {session_id} not found"
                )

            # Reset the session in the runner
            # This depends on your backend implementation

            # For database, we could do a soft reset by creating a new session with the same ID
            # and preserving metadata, but clearing messages
            # This is a simplified approach - in a real implementation, you might want to:
            # 1. Archive the old messages instead of deleting them
            # 2. Use a transaction to ensure atomicity
            try:
                # Delete all messages for this session
                # In a real implementation, you might want to move them to an archive table
                with get_chat_db_connection() as conn:
                    with get_chat_db_cursor(conn, commit=True) as cursor:
                        cursor.execute(
                            f"""
                            DELETE FROM {CHAT_SCHEMA}.chat_messages
                            WHERE session_id = %s;
                        """,
                            (uuid.UUID(session_id),),
                        )

                # Update session preview
                chat_operations.create_or_update_session(
                    session_id=session_id, preview="Session reset"
                )
            except Exception as db_error:
                logger.error(f"Database error during session reset: {db_error}")
                # Continue even if database reset fails

            return {"status": "success", "message": f"Session {session_id} reset"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error resetting session: %s", str(e), exc_info=True)
            raise HTTPException(
                status_code=500, detail=f"Error resetting session: {str(e)}"
            )

    @router.get("/{session_id}/stats")
    async def get_session_stats_endpoint(session_id: str = Path(...)):
        """Return token + cost stats for a session.

        Shape matches the frontend ``SessionStats`` interface (camelCase).
        Populated from ``llm_usage_log`` rows tagged with this ``session_id``.
        ``costTodayUsd`` / ``costMonthUsd`` are rolling totals across all sessions.
        """
        from radbot.telemetry.db import get_session_stats

        raw = get_session_stats(session_id)
        return {
            "inputTokens": raw["input_tokens"],
            "outputTokens": raw["output_tokens"],
            "contextTokens": raw["context_tokens"],
            "contextWindow": raw["context_window"],
            "model": raw["model"],
            "costUsd": raw["cost_usd"],
            "costTodayUsd": raw["cost_today_usd"],
            "costMonthUsd": raw["cost_month_usd"],
        }

    # Register the router with the app
    app.include_router(router)
    logger.debug("Sessions router registered")
