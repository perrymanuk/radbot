"""
FastAPI router for reminder management REST endpoints.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


class ReminderCreate(BaseModel):
    message: str
    remind_at: str  # ISO 8601 datetime
    timezone_name: str = "America/Los_Angeles"


class ReminderResponse(BaseModel):
    status: str
    reminder_id: Optional[str] = None
    message: Optional[str] = None


@router.get("")
async def list_reminders(status: str = "pending"):
    """List reminders, optionally filtered by status."""
    try:
        from radbot.tools.reminders.db import list_reminders as db_list
        from radbot.tools.shared.serialization import serialize_rows

        reminders = db_list(status=status if status != "all" else None)
        return serialize_rows(reminders)
    except Exception as e:
        logger.error(f"Error listing reminders: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=ReminderResponse)
async def create_reminder(body: ReminderCreate):
    """Create a new reminder via REST."""
    import zoneinfo

    # Parse datetime
    try:
        dt = datetime.fromisoformat(body.remind_at)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid datetime format: {body.remind_at}")

    # Apply timezone if naive
    if dt.tzinfo is None:
        try:
            tz = zoneinfo.ZoneInfo(body.timezone_name)
        except (KeyError, zoneinfo.ZoneInfoNotFoundError):
            raise HTTPException(status_code=400, detail=f"Unknown timezone: {body.timezone_name}")
        dt = dt.replace(tzinfo=tz)

    # Must be in the future
    if dt <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Reminder time must be in the future")

    try:
        from radbot.tools.reminders.db import create_reminder as db_create

        row = db_create(message=body.message, remind_at=dt)
        reminder_id = str(row["reminder_id"])

        # Register with the engine
        try:
            from radbot.tools.scheduler.engine import SchedulerEngine
            engine = SchedulerEngine.get_instance()
            if engine:
                engine.register_reminder(row)
        except Exception as e:
            logger.warning(f"Could not register with scheduler engine: {e}")

        return ReminderResponse(status="success", reminder_id=reminder_id)
    except Exception as e:
        logger.error(f"Error creating reminder: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{reminder_id}", response_model=ReminderResponse)
async def delete_reminder(reminder_id: str):
    """Cancel and delete a reminder by ID."""
    try:
        reminder_uuid = uuid.UUID(reminder_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    try:
        # Unregister from engine
        try:
            from radbot.tools.scheduler.engine import SchedulerEngine
            engine = SchedulerEngine.get_instance()
            if engine:
                engine.unregister_reminder(reminder_id)
        except Exception as e:
            logger.warning(f"Could not unregister from engine: {e}")

        from radbot.tools.reminders.db import delete_reminder as db_delete

        success = db_delete(reminder_uuid)
        if success:
            return ReminderResponse(status="success", reminder_id=reminder_id)
        else:
            raise HTTPException(status_code=404, detail="Reminder not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting reminder: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
