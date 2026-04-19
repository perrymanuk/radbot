"""
FastAPI router for notifications REST endpoints.
"""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class MarkAllReadRequest(BaseModel):
    type: Optional[str] = None


@router.get("/unread-count")
async def get_unread_count():
    """Return the count of unread notifications."""
    try:
        from radbot.tools.notifications.db import count_notifications

        count = count_notifications(read_filter=False)
        return {"count": count}
    except Exception as e:
        logger.error(f"Error getting unread count: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
async def list_notifications(
    type: Optional[str] = None,
    read: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """List notifications with optional filters."""
    try:
        from radbot.tools.notifications.db import (
            count_notifications,
        )
        from radbot.tools.notifications.db import list_notifications as db_list
        from radbot.tools.shared.serialization import serialize_rows

        read_filter = None
        if read == "true":
            read_filter = True
        elif read == "false":
            read_filter = False

        notifications = db_list(
            type_filter=type,
            read_filter=read_filter,
            limit=min(limit, 200),
            offset=offset,
        )
        total = count_notifications(type_filter=type, read_filter=read_filter)

        return {
            "notifications": serialize_rows(notifications),
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:
        logger.error(f"Error listing notifications: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{notification_id}")
async def get_notification(notification_id: str):
    """Get a single notification by ID."""
    try:
        nid = uuid.UUID(notification_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    try:
        from radbot.tools.notifications.db import get_notification as db_get
        from radbot.tools.shared.serialization import serialize_rows

        notification = db_get(nid)
        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")
        return serialize_rows([notification])[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting notification: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{notification_id}/read")
async def mark_notification_read(notification_id: str):
    """Mark a single notification as read."""
    try:
        nid = uuid.UUID(notification_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    try:
        from radbot.tools.notifications.db import mark_read

        mark_read(nid)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error marking notification read: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/read-all")
async def mark_all_notifications_read(body: MarkAllReadRequest = MarkAllReadRequest()):
    """Mark all notifications as read, optionally filtered by type."""
    try:
        from radbot.tools.notifications.db import mark_all_read

        count = mark_all_read(type_filter=body.type)
        return {"status": "ok", "count": count}
    except Exception as e:
        logger.error(f"Error marking all notifications read: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{notification_id}")
async def delete_notification(notification_id: str):
    """Delete a notification by ID."""
    try:
        nid = uuid.UUID(notification_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    try:
        from radbot.tools.notifications.db import delete_notification as db_delete

        success = db_delete(nid)
        if not success:
            raise HTTPException(status_code=404, detail="Notification not found")
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting notification: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
