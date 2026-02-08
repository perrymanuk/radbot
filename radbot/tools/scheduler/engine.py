"""
Scheduler engine wrapping APScheduler.

Singleton that loads scheduled tasks from the database, registers them as
APScheduler jobs, and fires prompts to the agent when jobs trigger.
Results are pushed to active WebSocket connections.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

# Singleton instance
_instance: Optional["SchedulerEngine"] = None


class SchedulerEngine:
    """Manages APScheduler lifecycle and job execution."""

    def __init__(self):
        self._scheduler = AsyncIOScheduler()
        self._connection_manager = None  # set by inject()
        self._started = False

    # -- singleton --
    @classmethod
    def get_instance(cls) -> Optional["SchedulerEngine"]:
        """Return the singleton, or None if not initialised yet."""
        return _instance

    @classmethod
    def create_instance(cls) -> "SchedulerEngine":
        """Create (or return existing) singleton."""
        global _instance
        if _instance is None:
            _instance = cls()
        return _instance

    # -- dependency injection --
    def inject(self, connection_manager: Any) -> None:
        """Inject the ConnectionManager for broadcasting notifications."""
        self._connection_manager = connection_manager

    # -- lifecycle --
    async def start(self) -> None:
        """Load all enabled tasks from the DB and start the scheduler."""
        if self._started:
            return

        try:
            from radbot.tools.scheduler.db import list_tasks
            tasks = list_tasks(enabled_only=True)
            logger.info(f"Loading {len(tasks)} enabled scheduled tasks")
            for task in tasks:
                self.register_job(task)
        except Exception as e:
            logger.error(f"Error loading scheduled tasks from DB: {e}")

        self._scheduler.start()
        self._started = True
        logger.info("SchedulerEngine started")

    async def shutdown(self) -> None:
        """Gracefully stop the scheduler."""
        if self._started:
            self._scheduler.shutdown(wait=False)
            self._started = False
            logger.info("SchedulerEngine shut down")

    # -- job management --
    def register_job(self, task_row: Dict[str, Any]) -> None:
        """Add or replace a job from a DB row dict."""
        task_id = str(task_row["task_id"])
        cron_expr = task_row["cron_expression"]
        prompt = task_row["prompt"]
        name = task_row.get("name", task_id)

        try:
            parts = cron_expr.strip().split()
            if len(parts) != 5:
                logger.error(f"Invalid cron expression for task {name}: '{cron_expr}'")
                return

            trigger = CronTrigger(
                minute=parts[0],
                hour=parts[1],
                day=parts[2],
                month=parts[3],
                day_of_week=parts[4],
            )
        except Exception as e:
            logger.error(f"Failed to parse cron expression '{cron_expr}' for task {name}: {e}")
            return

        # Remove existing job with same id if present
        existing = self._scheduler.get_job(task_id)
        if existing:
            existing.remove()

        self._scheduler.add_job(
            self._execute_job,
            trigger=trigger,
            id=task_id,
            name=name,
            kwargs={"task_id": task_id, "prompt": prompt, "name": name},
            replace_existing=True,
        )
        logger.info(f"Registered scheduler job '{name}' ({task_id}), cron='{cron_expr}'")

    def unregister_job(self, task_id: str) -> None:
        """Remove a job from the scheduler."""
        job = self._scheduler.get_job(task_id)
        if job:
            job.remove()
            logger.info(f"Unregistered scheduler job {task_id}")

    def get_next_run_time(self, task_id: str) -> Optional[datetime]:
        """Return the next fire time for a job, or None."""
        job = self._scheduler.get_job(task_id)
        if job and job.next_run_time:
            return job.next_run_time
        return None

    # -- execution --
    async def _execute_job(self, task_id: str, prompt: str, name: str) -> None:
        """Called by APScheduler when a job fires.

        Broadcasts the prompt directly as a notification to the web UI.
        The prompt is NOT sent to the LLM - it is the reminder message itself.
        """
        logger.info(f"=== SCHEDULER JOB FIRED === Task '{name}' ({task_id}), prompt: {prompt[:80]}")

        # Persist run in DB
        try:
            from radbot.tools.scheduler.db import update_last_run
            update_last_run(task_id, prompt[:4000])
        except Exception as e:
            logger.error(f"Failed to update last_run for scheduled task {task_id}: {e}")

        # Push directly to all active WebSocket connections (no LLM processing)
        if self._connection_manager:
            try:
                await self._broadcast_result(task_id, name, prompt)
            except Exception as e:
                logger.error(f"Failed to broadcast scheduled task result: {e}", exc_info=True)
        else:
            logger.warning(f"No connection_manager set, cannot broadcast task '{name}' result")

    async def _broadcast_result(
        self, task_id: str, name: str, prompt: str
    ) -> None:
        """Send the scheduled task notification to all active WebSocket connections."""
        if not self._connection_manager:
            logger.warning("No connection_manager available, cannot broadcast scheduled task result")
            return

        message_payload = {
            "type": "scheduled_task_result",
            "task_id": task_id,
            "task_name": name,
            "prompt": prompt,
            "timestamp": datetime.now().isoformat(),
        }

        # Iterate over a copy of the active connections
        connections = dict(self._connection_manager.active_connections)
        if not connections:
            logger.warning(f"No active WebSocket connections to broadcast scheduled task '{name}' result to")
            return

        logger.info(f"Broadcasting scheduled task '{name}' notification to {len(connections)} active connection(s)")
        sent_count = 0
        for session_id, ws in connections.items():
            try:
                await ws.send_json(message_payload)
                sent_count += 1
                logger.info(f"Sent scheduled task notification to session {session_id}")
            except Exception as e:
                logger.warning(f"Failed to send scheduled notification to session {session_id}: {e}")
        logger.info(f"Broadcast complete: sent to {sent_count}/{len(connections)} connections")
