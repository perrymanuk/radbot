"""
Scheduler engine wrapping APScheduler.

Singleton that loads scheduled tasks from the database, registers them as
APScheduler jobs, and fires prompts to the agent when jobs trigger.
Results are pushed to active WebSocket connections.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

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

        # Load pending reminders
        try:
            from radbot.tools.reminders.db import list_reminders
            reminders = list_reminders(status="pending")
            logger.info(f"Loading {len(reminders)} pending reminders")
            now = datetime.now(timezone.utc)
            for reminder in reminders:
                remind_at = reminder["remind_at"]
                if remind_at.tzinfo is None:
                    remind_at = remind_at.replace(tzinfo=timezone.utc)
                if remind_at <= now:
                    # Past-due: mark completed but undelivered
                    logger.info(f"Reminder {reminder['reminder_id']} is past-due, marking completed (undelivered)")
                    from radbot.tools.reminders.db import mark_completed
                    mark_completed(reminder["reminder_id"])
                else:
                    self.register_reminder(reminder)
        except Exception as e:
            logger.error(f"Error loading reminders from DB: {e}")

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
    async def _send_ntfy(self, title: str, message: str, tags: str = "robot", session_id: Optional[str] = None) -> None:
        """Send a push notification via ntfy if configured."""
        try:
            from radbot.tools.ntfy.ntfy_client import get_ntfy_client
            client = get_ntfy_client()
            if not client:
                logger.debug("ntfy client not available (unconfigured or disabled)")
                return
            await client.publish(
                title=title,
                message=message,
                tags=tags,
                session_id=session_id,
            )
        except Exception as e:
            logger.warning(f"ntfy notification failed (non-fatal): {e}")

    async def _execute_job(self, task_id: str, prompt: str, name: str) -> None:
        """Called by APScheduler when a job fires.

        Always processes the prompt through the agent regardless of WebSocket
        connection state. Results are broadcast to active connections and/or
        queued for delivery on reconnect. A push notification is sent via ntfy.
        """
        from radbot.tools.shared.sanitize import sanitize_text
        prompt = sanitize_text(prompt, source="scheduler")
        logger.info(f"=== SCHEDULER JOB FIRED === Task '{name}' ({task_id}), prompt: {prompt[:80]}")

        if not self._connection_manager:
            logger.warning(f"No connection_manager set, cannot process task '{name}'")
            self._update_last_run(task_id, "skipped: no connection manager")
            return

        has_connections = self._connection_manager.has_connections()

        # Pick a session_id: use an active connection's session, or generate
        # a fixed offline session ID so the agent can still process.
        if has_connections:
            session_id = self._connection_manager.get_any_session_id()
        else:
            session_id = "scheduler-offline"
            logger.info(f"No active WebSocket connections; using offline session for task '{name}'")

        logger.info(f"Using session {session_id} for scheduled task '{name}' processing")

        # 1. Broadcast system message to all connections (no-op if none)
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

            # 9. Send push notification via ntfy
            await self._send_ntfy(
                title=f"Scheduled: {name}",
                message=response[:2000] if response else "(no response)",
                tags="robot,clock",
                session_id=session_id,
            )

            # 10. If no WS connections were active, queue result for reconnect delivery
            if not has_connections and response:
                try:
                    from radbot.tools.scheduler.db import queue_pending_result
                    queue_pending_result(
                        task_name=name,
                        prompt=prompt,
                        response=response[:4000],
                        session_id=session_id,
                    )
                    logger.info(f"Queued offline result for task '{name}' for later WS delivery")
                except Exception as q_err:
                    logger.warning(f"Failed to queue pending result: {q_err}")

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

    # -- reminder management --
    def register_reminder(self, reminder_row: Dict[str, Any]) -> None:
        """Register a one-shot reminder as a DateTrigger job."""
        reminder_id = str(reminder_row["reminder_id"])
        job_id = f"reminder_{reminder_id}"
        message = reminder_row["message"]
        remind_at = reminder_row["remind_at"]

        # Ensure timezone-aware
        if remind_at.tzinfo is None:
            remind_at = remind_at.replace(tzinfo=timezone.utc)

        # Remove existing job if present
        existing = self._scheduler.get_job(job_id)
        if existing:
            existing.remove()

        try:
            trigger = DateTrigger(run_date=remind_at)
            self._scheduler.add_job(
                self._execute_reminder,
                trigger=trigger,
                id=job_id,
                name=f"Reminder: {message[:50]}",
                kwargs={"reminder_id": reminder_id, "message": message},
                replace_existing=True,
            )
            logger.info(f"Registered reminder '{message[:50]}' ({reminder_id}), fires at {remind_at.isoformat()}")
        except Exception as e:
            logger.error(f"Failed to register reminder {reminder_id}: {e}")

    def unregister_reminder(self, reminder_id: str) -> None:
        """Remove a reminder job from the scheduler."""
        job_id = f"reminder_{reminder_id}"
        job = self._scheduler.get_job(job_id)
        if job:
            job.remove()
            logger.info(f"Unregistered reminder job {reminder_id}")

    async def _execute_reminder(self, reminder_id: str, message: str) -> None:
        """Called by APScheduler when a reminder fires.

        Always marks the reminder completed and sends a push notification.
        If WebSocket connections are active, broadcasts the reminder.
        Otherwise leaves it undelivered for reconnect delivery.
        """
        logger.info(f"=== REMINDER FIRED === ({reminder_id}): {message[:80]}")

        # 1. Always mark completed in DB
        try:
            from radbot.tools.reminders.db import mark_completed
            mark_completed(reminder_id)
        except Exception as e:
            logger.error(f"Failed to mark reminder {reminder_id} completed: {e}")

        # 2. Always send push notification via ntfy
        await self._send_ntfy(
            title="Reminder",
            message=message,
            tags="bell",
        )

        # 3. Check if we can deliver via WS now
        if not self._connection_manager or not self._connection_manager.has_connections():
            logger.info(f"No active connections, reminder {reminder_id} will be delivered on reconnect")
            return

        # 4. Deliver the reminder via WebSocket
        await self._deliver_single_reminder(reminder_id, message)

    async def _deliver_single_reminder(self, reminder_id: str, message: str) -> None:
        """Deliver a single reminder as a notification broadcast. No LLM processing."""
        from radbot.tools.shared.sanitize import sanitize_text
        message = sanitize_text(message, source="reminder")
        session_id = self._connection_manager.get_any_session_id()
        if not session_id:
            return

        system_content = f"[Reminder] {message}"

        # Broadcast as a system message notification
        await self._broadcast_to_all({
            "type": "message",
            "role": "system",
            "content": system_content,
        })

        # Persist to chat history DB
        try:
            from radbot.web.db import chat_operations
            chat_operations.add_message(session_id, "system", system_content, user_id="web_user")
        except Exception as e:
            logger.warning(f"Failed to persist reminder system message to DB: {e}")

        # Mark delivered
        try:
            from radbot.tools.reminders.db import mark_delivered
            mark_delivered(reminder_id, "delivered")
        except Exception as e:
            logger.error(f"Failed to mark reminder {reminder_id} delivered: {e}")

        logger.info(f"Reminder {reminder_id} delivered as notification")

    async def deliver_pending_reminders(self) -> None:
        """Deliver any completed-but-undelivered reminders.

        Called when a WebSocket connection is established, to catch up on
        reminders that fired while no connections were active.
        """
        try:
            from radbot.tools.reminders.db import get_undelivered_completed
            undelivered = get_undelivered_completed()
            if not undelivered:
                return

            logger.info(f"Delivering {len(undelivered)} pending reminders on reconnect")
            for reminder in undelivered:
                reminder_id = str(reminder["reminder_id"])
                message = reminder["message"]
                await self._deliver_single_reminder(reminder_id, message)
        except Exception as e:
            logger.error(f"Error delivering pending reminders: {e}", exc_info=True)

    async def deliver_pending_scheduler_results(self) -> None:
        """Deliver any queued scheduler results from offline execution.

        Called when a WebSocket connection is established, to catch up on
        scheduled task results that ran while no connections were active.
        """
        try:
            from radbot.tools.scheduler.db import get_undelivered_results, mark_result_delivered
            undelivered = get_undelivered_results()
            if not undelivered:
                return

            logger.info(f"Delivering {len(undelivered)} pending scheduler results on reconnect")
            for row in undelivered:
                result_id = row["result_id"]
                task_name = row["task_name"]
                response = row.get("response", "")

                system_content = f"[Offline Scheduled Task: {task_name}] {response}"
                await self._broadcast_to_all({
                    "type": "message",
                    "role": "system",
                    "content": system_content,
                })

                try:
                    mark_result_delivered(result_id)
                except Exception as e:
                    logger.error(f"Failed to mark result {result_id} delivered: {e}")

                logger.info(f"Delivered pending result for task '{task_name}'")
        except Exception as e:
            logger.error(f"Error delivering pending scheduler results: {e}", exc_info=True)

    def _update_last_run(self, task_id: str, result: str) -> None:
        """Update the last_run_at timestamp in the DB."""
        try:
            from radbot.tools.scheduler.db import update_last_run
            update_last_run(task_id, result)
        except Exception as e:
            logger.error(f"Failed to update last_run for scheduled task {task_id}: {e}")
