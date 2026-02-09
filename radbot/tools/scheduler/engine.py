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
        self._session_manager = None  # set by inject()
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
    def inject(self, connection_manager: Any, session_manager: Any = None) -> None:
        """Inject the ConnectionManager and optional SessionManager."""
        self._connection_manager = connection_manager
        self._session_manager = session_manager

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

    # -- helpers --
    async def _broadcast_to_all(self, payload: dict) -> int:
        """Send a JSON payload to ALL active WebSocket connections.

        Returns the number of successful sends.
        """
        if not self._connection_manager:
            return 0
        return await self._connection_manager.broadcast_to_all_sessions(payload)

    # -- execution --
    async def _execute_job(self, task_id: str, prompt: str, name: str) -> None:
        """Called by APScheduler when a job fires.

        Processes the prompt through the agent and broadcasts results to all
        active WebSocket connections.
        """
        logger.info(f"=== SCHEDULER JOB FIRED === Task '{name}' ({task_id}), prompt: {prompt[:80]}")

        # Snapshot active connections; skip if none
        if not self._connection_manager:
            logger.warning(f"No connection_manager set, cannot process task '{name}'")
            self._update_last_run(task_id, "skipped: no connection manager")
            return

        if not self._connection_manager.has_connections():
            logger.info(f"No active WebSocket connections, skipping task '{name}'")
            self._update_last_run(task_id, "skipped: no active connections")
            return

        # Pick the first active session_id for agent processing
        session_id = self._connection_manager.get_any_session_id()
        logger.info(f"Using session {session_id} for scheduled task '{name}' processing")

        # 1. Broadcast system message to all connections
        system_content = f"[Scheduled Task: {name}] {prompt}"
        await self._broadcast_to_all({
            "type": "message",
            "role": "system",
            "content": system_content,
        })

        # 2. Broadcast "thinking" status
        await self._broadcast_to_all({
            "type": "status",
            "content": "thinking",
        })

        # 3. Persist system message to DB
        try:
            from radbot.web.db import chat_operations
            chat_operations.add_message(session_id, "system", system_content, user_id="web_user")
        except Exception as e:
            logger.warning(f"Failed to persist system message to DB: {e}")

        # 4. Process through agent
        try:
            # Lazy import to avoid circular dependencies
            from radbot.web.api.session.dependencies import get_or_create_runner_for_session

            runner = await get_or_create_runner_for_session(session_id, self._session_manager)
            result = await runner.process_message(prompt)

            response = result.get("response", "")
            events = result.get("events", [])

            # 5. Persist assistant response to DB
            if response:
                try:
                    from radbot.web.db import chat_operations
                    chat_operations.add_message(session_id, "assistant", response, user_id="web_user")
                except Exception as e:
                    logger.warning(f"Failed to persist assistant response to DB: {e}")

            # 6. Broadcast events to all connections
            if events:
                sent = await self._broadcast_to_all({
                    "type": "events",
                    "content": events,
                })
                logger.info(f"Broadcast {len(events)} events to {sent} connections")

            # 7. Broadcast "ready" status
            await self._broadcast_to_all({
                "type": "status",
                "content": "ready",
            })

            # 8. Update last run in DB
            self._update_last_run(task_id, response[:4000] if response else "completed (no response)")

            logger.info(f"Scheduled task '{name}' processed successfully")

        except Exception as e:
            logger.error(f"Error processing scheduled task '{name}': {e}", exc_info=True)

            # Broadcast error and ready status
            await self._broadcast_to_all({
                "type": "status",
                "content": f"error: Scheduled task '{name}' failed: {e}",
            })
            await self._broadcast_to_all({
                "type": "status",
                "content": "ready",
            })

            self._update_last_run(task_id, f"error: {str(e)[:4000]}")

    def _update_last_run(self, task_id: str, result: str) -> None:
        """Update the last_run_at timestamp in the DB."""
        try:
            from radbot.tools.scheduler.db import update_last_run
            update_last_run(task_id, result)
        except Exception as e:
            logger.error(f"Failed to update last_run for scheduled task {task_id}: {e}")
