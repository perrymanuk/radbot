"""
Agent tools for scheduled task management.

Provides create, list, and delete tools that the agent can invoke to manage
recurring scheduled tasks.
"""

import logging
import traceback
import uuid
from typing import Dict, Any, Optional

from google.adk.tools import FunctionTool

from . import db as scheduler_db

logger = logging.getLogger(__name__)


def create_scheduled_task(
    name: str,
    cron_expression: str,
    prompt: str,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Creates a new recurring scheduled task.

    The task will fire on the given cron schedule, send the prompt to the agent,
    and push the response to the web UI.

    Args:
        name: A short human-readable name for the task (e.g. "Morning Weather Check").
        cron_expression: A cron expression defining the schedule
            (e.g. "0 9 * * *" for every day at 9 AM, "*/30 * * * *" for every 30 minutes).
            Format: minute hour day_of_month month day_of_week
        prompt: The text that will be sent to the agent each time the task fires.
        description: An optional longer description of what this task does.

    Returns:
        On success: {"status": "success", "task_id": "...", "name": "...", "cron_expression": "..."}
        On failure: {"status": "error", "message": "..."}
    """
    try:
        row = scheduler_db.create_task(
            name=name,
            cron_expression=cron_expression,
            prompt=prompt,
            description=description,
        )
        task_id = str(row["task_id"])

        # Register with the running scheduler engine if it exists
        try:
            from radbot.tools.scheduler.engine import SchedulerEngine
            engine = SchedulerEngine.get_instance()
            if engine:
                engine.register_job(row)
        except Exception as e:
            logger.warning(f"Could not register job with scheduler engine: {e}")

        return {
            "status": "success",
            "task_id": task_id,
            "name": name,
            "cron_expression": cron_expression,
        }
    except Exception as e:
        error_message = f"Failed to create scheduled task: {str(e)}"
        logger.error(f"Error in create_scheduled_task: {error_message}")
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": error_message[:200]}


def list_scheduled_tasks() -> Dict[str, Any]:
    """
    Lists all scheduled tasks with their status and next run time.

    Returns:
        On success: {"status": "success", "tasks": [...]}
        On failure: {"status": "error", "message": "..."}
    """
    try:
        tasks = scheduler_db.list_tasks()

        # Enrich with next run time from the engine if available
        try:
            from radbot.tools.scheduler.engine import SchedulerEngine
            engine = SchedulerEngine.get_instance()
            if engine:
                for task in tasks:
                    next_run = engine.get_next_run_time(str(task["task_id"]))
                    task["next_run_at"] = next_run.isoformat() if next_run else None
        except Exception:
            pass

        # Serialise UUIDs and datetimes
        serialised = []
        for t in tasks:
            item = {}
            for k, v in t.items():
                if isinstance(v, uuid.UUID):
                    item[k] = str(v)
                elif hasattr(v, "isoformat"):
                    item[k] = v.isoformat()
                else:
                    item[k] = v
            serialised.append(item)

        return {"status": "success", "tasks": serialised}
    except Exception as e:
        error_message = f"Failed to list scheduled tasks: {str(e)}"
        logger.error(f"Error in list_scheduled_tasks: {error_message}")
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": error_message[:200]}


def delete_scheduled_task(task_id: str) -> Dict[str, Any]:
    """
    Deletes a scheduled task by its UUID.

    Args:
        task_id: The UUID of the scheduled task to delete.

    Returns:
        On success: {"status": "success", "task_id": "..."}
        On failure: {"status": "error", "message": "..."}
    """
    try:
        try:
            task_uuid = uuid.UUID(task_id)
        except ValueError:
            return {
                "status": "error",
                "message": f"Invalid task ID format: {task_id}. Must be a valid UUID.",
            }

        # Unregister from the running engine first
        try:
            from radbot.tools.scheduler.engine import SchedulerEngine
            engine = SchedulerEngine.get_instance()
            if engine:
                engine.unregister_job(task_id)
        except Exception as e:
            logger.warning(f"Could not unregister job from scheduler engine: {e}")

        success = scheduler_db.delete_task(task_uuid)
        if success:
            return {"status": "success", "task_id": task_id}
        else:
            return {
                "status": "error",
                "message": f"Scheduled task {task_id} not found.",
            }
    except Exception as e:
        error_message = f"Failed to delete scheduled task: {str(e)}"
        logger.error(f"Error in delete_scheduled_task: {error_message}")
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": error_message[:200]}


# Wrap as ADK FunctionTools
create_scheduled_task_tool = FunctionTool(create_scheduled_task)
list_scheduled_tasks_tool = FunctionTool(list_scheduled_tasks)
delete_scheduled_task_tool = FunctionTool(delete_scheduled_task)

SCHEDULER_TOOLS = [
    create_scheduled_task_tool,
    list_scheduled_tasks_tool,
    delete_scheduled_task_tool,
]
