"""
Agent tools for one-shot reminder management.

Provides create, list, and delete tools that the agent can invoke to manage
reminders that fire at a specific datetime.
"""

import logging
import traceback
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from google.adk.tools import FunctionTool

from . import db as reminder_db

logger = logging.getLogger(__name__)


def create_reminder(
    message: str,
    remind_at: str = "",
    delay_minutes: float = 0,
    timezone_name: str = "America/Los_Angeles",
) -> Dict[str, Any]:
    """
    Creates a one-shot reminder that fires at a specific date and time.

    Use this when the user says things like "remind me tomorrow at 9am to call the dentist",
    "set a reminder for Friday at 3pm to submit the report", or "remind me in 2 hours to
    check the oven".

    For RELATIVE times like "in 2 minutes", "in an hour", "in 30 minutes", use the
    delay_minutes parameter instead of remind_at. This is the easiest and most reliable
    approach for relative reminders. Examples:
      - "in 2 minutes" -> delay_minutes=2
      - "in an hour" -> delay_minutes=60
      - "in 30 seconds" -> delay_minutes=0.5
      - "in 90 minutes" -> delay_minutes=90

    For ABSOLUTE times like "tomorrow at 9am", "Friday at 3pm", use the remind_at parameter
    with an ISO 8601 datetime string. You MUST call get_current_time first to know the
    current date and time so you can compute the correct datetime.

    You must provide either remind_at OR delay_minutes (not both empty).

    Args:
        message: The reminder message describing what to remind the user about
            (e.g. "call the dentist", "submit the report", "check the oven").
        remind_at: ISO 8601 datetime string for when the reminder should fire
            (e.g. "2025-01-15T09:00:00", "2025-01-17T15:00:00-08:00").
            If no timezone offset is included, the timezone_name parameter is used.
            Leave empty if using delay_minutes instead.
        delay_minutes: Number of minutes from now to fire the reminder.
            Use this for relative times like "in 5 minutes" (set to 5),
            "in an hour" (set to 60), "in 30 seconds" (set to 0.5).
            Leave as 0 if using remind_at instead.
        timezone_name: IANA timezone name to apply if remind_at has no timezone offset.
            Defaults to "America/Los_Angeles" (Pacific Time).

    Returns:
        On success: {"status": "success", "reminder_id": "...", "message": "...", "remind_at": "..."}
        On failure: {"status": "error", "message": "..."}
    """
    try:
        import zoneinfo
        from datetime import timedelta

        # Determine the target datetime
        if delay_minutes and delay_minutes > 0:
            # Relative time: compute from now
            dt = datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)
        elif remind_at:
            # Absolute time: parse ISO 8601
            try:
                dt = datetime.fromisoformat(remind_at)
            except ValueError:
                return {
                    "status": "error",
                    "message": f"Invalid datetime format: '{remind_at}'. Use ISO 8601 format (e.g. 2025-01-15T09:00:00).",
                }

            # Apply timezone if naive
            if dt.tzinfo is None:
                try:
                    tz = zoneinfo.ZoneInfo(timezone_name)
                except (KeyError, zoneinfo.ZoneInfoNotFoundError):
                    return {
                        "status": "error",
                        "message": f"Unknown timezone: '{timezone_name}'. Use an IANA timezone name (e.g. America/Los_Angeles).",
                    }
                dt = dt.replace(tzinfo=tz)
        else:
            return {
                "status": "error",
                "message": "You must provide either remind_at (ISO datetime) or delay_minutes (number > 0).",
            }

        # Validate it's in the future
        now = datetime.now(timezone.utc)
        if dt <= now:
            return {
                "status": "error",
                "message": f"Reminder time {dt.isoformat()} is in the past. Please specify a future time.",
            }

        # Persist to DB
        row = reminder_db.create_reminder(
            message=message,
            remind_at=dt,
        )
        reminder_id = str(row["reminder_id"])

        # Register with the scheduler engine if running
        try:
            from radbot.tools.scheduler.engine import SchedulerEngine
            engine = SchedulerEngine.get_instance()
            if engine:
                engine.register_reminder(row)
        except Exception as e:
            logger.warning(f"Could not register reminder with scheduler engine: {e}")

        return {
            "status": "success",
            "reminder_id": reminder_id,
            "message": message,
            "remind_at": dt.isoformat(),
        }
    except Exception as e:
        error_message = f"Failed to create reminder: {str(e)}"
        logger.error(f"Error in create_reminder: {error_message}")
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": error_message[:200]}


def list_reminders(status: str = "pending") -> Dict[str, Any]:
    """
    Lists reminders filtered by status.

    Args:
        status: Filter by status. One of: "pending", "completed", "cancelled", "all".
            Defaults to "pending" to show only upcoming reminders.

    Returns:
        On success: {"status": "success", "reminders": [...]}
        On failure: {"status": "error", "message": "..."}
    """
    try:
        reminders = reminder_db.list_reminders(status=status if status != "all" else None)

        # Serialise UUIDs and datetimes
        serialised = []
        for r in reminders:
            item = {}
            for k, v in r.items():
                if isinstance(v, uuid.UUID):
                    item[k] = str(v)
                elif hasattr(v, "isoformat"):
                    item[k] = v.isoformat()
                else:
                    item[k] = v
            serialised.append(item)

        return {"status": "success", "reminders": serialised}
    except Exception as e:
        error_message = f"Failed to list reminders: {str(e)}"
        logger.error(f"Error in list_reminders: {error_message}")
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": error_message[:200]}


def delete_reminder(reminder_id: str) -> Dict[str, Any]:
    """
    Cancels and deletes a reminder by its UUID.

    Args:
        reminder_id: The UUID of the reminder to cancel and delete.

    Returns:
        On success: {"status": "success", "reminder_id": "..."}
        On failure: {"status": "error", "message": "..."}
    """
    try:
        try:
            reminder_uuid = uuid.UUID(reminder_id)
        except ValueError:
            return {
                "status": "error",
                "message": f"Invalid reminder ID format: {reminder_id}. Must be a valid UUID.",
            }

        # Unregister from the running engine first
        try:
            from radbot.tools.scheduler.engine import SchedulerEngine
            engine = SchedulerEngine.get_instance()
            if engine:
                engine.unregister_reminder(reminder_id)
        except Exception as e:
            logger.warning(f"Could not unregister reminder from scheduler engine: {e}")

        success = reminder_db.delete_reminder(reminder_uuid)
        if success:
            return {"status": "success", "reminder_id": reminder_id}
        else:
            return {
                "status": "error",
                "message": f"Reminder {reminder_id} not found.",
            }
    except Exception as e:
        error_message = f"Failed to delete reminder: {str(e)}"
        logger.error(f"Error in delete_reminder: {error_message}")
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": error_message[:200]}


# Wrap as ADK FunctionTools
create_reminder_tool = FunctionTool(create_reminder)
list_reminders_tool = FunctionTool(list_reminders)
delete_reminder_tool = FunctionTool(delete_reminder)

REMINDER_TOOLS = [
    create_reminder_tool,
    list_reminders_tool,
    delete_reminder_tool,
]
