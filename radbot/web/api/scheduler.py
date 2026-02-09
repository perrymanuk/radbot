"""
FastAPI router for scheduler management REST endpoints.
"""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


class ScheduledTaskCreate(BaseModel):
    name: str
    cron_expression: str
    prompt: str
    description: Optional[str] = None


class ScheduledTaskResponse(BaseModel):
    status: str
    task_id: Optional[str] = None
    message: Optional[str] = None


@router.get("/tasks")
async def list_scheduled_tasks():
    """List all scheduled tasks."""
    try:
        from radbot.tools.scheduler.db import list_tasks
        from radbot.tools.shared.serialization import serialize_rows
        tasks = list_tasks()
        return serialize_rows(tasks)
    except Exception as e:
        logger.error(f"Error listing scheduled tasks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks", response_model=ScheduledTaskResponse)
async def create_scheduled_task(body: ScheduledTaskCreate):
    """Create a new scheduled task via REST."""
    try:
        from radbot.tools.scheduler.db import create_task
        row = create_task(
            name=body.name,
            cron_expression=body.cron_expression,
            prompt=body.prompt,
            description=body.description,
        )

        task_id = str(row["task_id"])

        # Register with the engine
        try:
            from radbot.tools.scheduler.engine import SchedulerEngine
            engine = SchedulerEngine.get_instance()
            if engine:
                engine.register_job(row)
        except Exception as e:
            logger.warning(f"Could not register with scheduler engine: {e}")

        return ScheduledTaskResponse(status="success", task_id=task_id)
    except Exception as e:
        logger.error(f"Error creating scheduled task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks/{task_id}/trigger")
async def trigger_scheduled_task(task_id: str):
    """Manually trigger a scheduled task for testing. Runs the task immediately."""
    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    try:
        from radbot.tools.scheduler.engine import SchedulerEngine
        engine = SchedulerEngine.get_instance()
        if not engine:
            raise HTTPException(status_code=503, detail="Scheduler engine not running")

        # Look up the task from DB
        from radbot.tools.scheduler.db import list_tasks
        tasks = list_tasks()
        task = next((t for t in tasks if str(t["task_id"]) == task_id), None)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        # Fire the job directly (fast - just broadcasts, no LLM)
        await engine._execute_job(
            task_id=task_id,
            prompt=task["prompt"],
            name=task.get("name", task_id),
        )

        return {"status": "triggered", "task_id": task_id, "name": task.get("name")}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering scheduled task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/tasks/{task_id}", response_model=ScheduledTaskResponse)
async def delete_scheduled_task(task_id: str):
    """Delete a scheduled task by ID."""
    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    try:
        # Unregister from engine
        try:
            from radbot.tools.scheduler.engine import SchedulerEngine
            engine = SchedulerEngine.get_instance()
            if engine:
                engine.unregister_job(task_id)
        except Exception as e:
            logger.warning(f"Could not unregister from engine: {e}")

        from radbot.tools.scheduler.db import delete_task
        success = delete_task(task_uuid)
        if success:
            return ScheduledTaskResponse(status="success", task_id=task_id)
        else:
            raise HTTPException(status_code=404, detail="Task not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting scheduled task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
