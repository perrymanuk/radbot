"""
Unit tests for the scheduler engine and reminder tools.

Tests cover:
- SchedulerEngine singleton pattern
- Start/stop lifecycle
- Job registration/unregistration with APScheduler
- Reminder registration with DateTrigger
- Loading tasks and reminders from DB on startup
- Reminder tool functions (create, list, delete)
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest import mock
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# SchedulerEngine tests
# ---------------------------------------------------------------------------


class TestSchedulerEngineSingleton:
    """Singleton pattern works correctly."""

    def setup_method(self):
        """Reset the module-level singleton before each test."""
        import radbot.tools.scheduler.engine as engine_mod

        engine_mod._instance = None

    def test_get_instance_returns_none_before_creation(self):
        from radbot.tools.scheduler.engine import SchedulerEngine

        assert SchedulerEngine.get_instance() is None

    def test_create_instance_returns_engine(self):
        from radbot.tools.scheduler.engine import SchedulerEngine

        engine = SchedulerEngine.create_instance()
        assert engine is not None
        assert isinstance(engine, SchedulerEngine)

    def test_create_instance_returns_same_instance(self):
        from radbot.tools.scheduler.engine import SchedulerEngine

        engine1 = SchedulerEngine.create_instance()
        engine2 = SchedulerEngine.create_instance()
        assert engine1 is engine2

    def test_get_instance_returns_created_instance(self):
        from radbot.tools.scheduler.engine import SchedulerEngine

        engine = SchedulerEngine.create_instance()
        assert SchedulerEngine.get_instance() is engine


class TestSchedulerEngineLifecycle:
    """Start/stop lifecycle."""

    def setup_method(self):
        import radbot.tools.scheduler.engine as engine_mod

        engine_mod._instance = None

    @pytest.mark.asyncio
    async def test_start_sets_started_flag(self):
        from radbot.tools.scheduler.engine import SchedulerEngine

        engine = SchedulerEngine.create_instance()
        engine._scheduler = MagicMock()

        with (
            patch("radbot.tools.scheduler.engine.SchedulerEngine.register_job"),
            patch("radbot.tools.scheduler.db.list_tasks", return_value=[]),
            patch("radbot.tools.reminders.db.list_reminders", return_value=[]),
        ):
            await engine.start()

        assert engine._started is True
        engine._scheduler.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_is_idempotent(self):
        from radbot.tools.scheduler.engine import SchedulerEngine

        engine = SchedulerEngine.create_instance()
        engine._scheduler = MagicMock()

        with (
            patch("radbot.tools.scheduler.db.list_tasks", return_value=[]),
            patch("radbot.tools.reminders.db.list_reminders", return_value=[]),
        ):
            await engine.start()
            await engine.start()  # second call should be no-op

        engine._scheduler.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_stops_scheduler(self):
        from radbot.tools.scheduler.engine import SchedulerEngine

        engine = SchedulerEngine.create_instance()
        engine._scheduler = MagicMock()
        engine._started = True

        await engine.shutdown()

        assert engine._started is False
        engine._scheduler.shutdown.assert_called_once_with(wait=False)

    @pytest.mark.asyncio
    async def test_shutdown_noop_when_not_started(self):
        from radbot.tools.scheduler.engine import SchedulerEngine

        engine = SchedulerEngine.create_instance()
        engine._scheduler = MagicMock()

        await engine.shutdown()

        engine._scheduler.shutdown.assert_not_called()


class TestSchedulerEngineRegisterJob:
    """register_job with CronTrigger."""

    def setup_method(self):
        import radbot.tools.scheduler.engine as engine_mod

        engine_mod._instance = None

    def test_register_job_calls_add_job(self):
        from radbot.tools.scheduler.engine import SchedulerEngine

        engine = SchedulerEngine.create_instance()
        engine._scheduler = MagicMock()
        engine._scheduler.get_job.return_value = None

        task_row = {
            "task_id": "11111111-1111-1111-1111-111111111111",
            "cron_expression": "0 9 * * *",
            "prompt": "Good morning check",
            "name": "morning-check",
        }

        engine.register_job(task_row)

        engine._scheduler.add_job.assert_called_once()
        call_kwargs = engine._scheduler.add_job.call_args
        assert call_kwargs.kwargs["id"] == "11111111-1111-1111-1111-111111111111"
        assert call_kwargs.kwargs["name"] == "morning-check"
        assert call_kwargs.kwargs["replace_existing"] is True

    def test_register_job_removes_existing_before_add(self):
        from radbot.tools.scheduler.engine import SchedulerEngine

        engine = SchedulerEngine.create_instance()
        existing_job = MagicMock()
        engine._scheduler = MagicMock()
        engine._scheduler.get_job.return_value = existing_job

        task_row = {
            "task_id": "22222222-2222-2222-2222-222222222222",
            "cron_expression": "*/5 * * * *",
            "prompt": "Check status",
            "name": "status-check",
        }

        engine.register_job(task_row)

        existing_job.remove.assert_called_once()
        engine._scheduler.add_job.assert_called_once()

    def test_register_job_rejects_invalid_cron(self):
        from radbot.tools.scheduler.engine import SchedulerEngine

        engine = SchedulerEngine.create_instance()
        engine._scheduler = MagicMock()

        task_row = {
            "task_id": "33333333-3333-3333-3333-333333333333",
            "cron_expression": "bad cron",
            "prompt": "Test",
            "name": "bad-job",
        }

        engine.register_job(task_row)

        engine._scheduler.add_job.assert_not_called()

    def test_register_job_uses_task_id_as_name_fallback(self):
        from radbot.tools.scheduler.engine import SchedulerEngine

        engine = SchedulerEngine.create_instance()
        engine._scheduler = MagicMock()
        engine._scheduler.get_job.return_value = None

        task_row = {
            "task_id": "44444444-4444-4444-4444-444444444444",
            "cron_expression": "0 12 * * 1",
            "prompt": "Weekly check",
            # no "name" key
        }

        engine.register_job(task_row)

        call_kwargs = engine._scheduler.add_job.call_args
        assert call_kwargs.kwargs["name"] == "44444444-4444-4444-4444-444444444444"


class TestSchedulerEngineUnregisterJob:
    """unregister_job removes the job."""

    def setup_method(self):
        import radbot.tools.scheduler.engine as engine_mod

        engine_mod._instance = None

    def test_unregister_job_removes_existing(self):
        from radbot.tools.scheduler.engine import SchedulerEngine

        engine = SchedulerEngine.create_instance()
        mock_job = MagicMock()
        engine._scheduler = MagicMock()
        engine._scheduler.get_job.return_value = mock_job

        engine.unregister_job("some-task-id")

        engine._scheduler.get_job.assert_called_once_with("some-task-id")
        mock_job.remove.assert_called_once()

    def test_unregister_job_noop_when_not_found(self):
        from radbot.tools.scheduler.engine import SchedulerEngine

        engine = SchedulerEngine.create_instance()
        engine._scheduler = MagicMock()
        engine._scheduler.get_job.return_value = None

        engine.unregister_job("nonexistent-id")

        engine._scheduler.get_job.assert_called_once_with("nonexistent-id")


class TestSchedulerEngineRegisterReminder:
    """register_reminder with DateTrigger."""

    def setup_method(self):
        import radbot.tools.scheduler.engine as engine_mod

        engine_mod._instance = None

    def test_register_reminder_calls_add_job(self):
        from radbot.tools.scheduler.engine import SchedulerEngine

        engine = SchedulerEngine.create_instance()
        engine._scheduler = MagicMock()
        engine._scheduler.get_job.return_value = None

        remind_at = datetime.now(timezone.utc) + timedelta(hours=1)
        reminder_row = {
            "reminder_id": "aaaa1111-1111-1111-1111-111111111111",
            "message": "Call the dentist",
            "remind_at": remind_at,
        }

        engine.register_reminder(reminder_row)

        engine._scheduler.add_job.assert_called_once()
        call_kwargs = engine._scheduler.add_job.call_args
        assert (
            call_kwargs.kwargs["id"] == "reminder_aaaa1111-1111-1111-1111-111111111111"
        )
        assert call_kwargs.kwargs["replace_existing"] is True

    def test_register_reminder_handles_naive_datetime(self):
        from radbot.tools.scheduler.engine import SchedulerEngine

        engine = SchedulerEngine.create_instance()
        engine._scheduler = MagicMock()
        engine._scheduler.get_job.return_value = None

        # naive datetime (no tzinfo)
        remind_at = datetime(2030, 6, 15, 10, 0, 0)
        reminder_row = {
            "reminder_id": "bbbb2222-2222-2222-2222-222222222222",
            "message": "Naive tz reminder",
            "remind_at": remind_at,
        }

        engine.register_reminder(reminder_row)

        engine._scheduler.add_job.assert_called_once()

    def test_register_reminder_removes_existing(self):
        from radbot.tools.scheduler.engine import SchedulerEngine

        engine = SchedulerEngine.create_instance()
        existing_job = MagicMock()
        engine._scheduler = MagicMock()
        engine._scheduler.get_job.return_value = existing_job

        remind_at = datetime.now(timezone.utc) + timedelta(hours=2)
        reminder_row = {
            "reminder_id": "cccc3333-3333-3333-3333-333333333333",
            "message": "Replacement reminder",
            "remind_at": remind_at,
        }

        engine.register_reminder(reminder_row)

        existing_job.remove.assert_called_once()

    def test_unregister_reminder_removes_job(self):
        from radbot.tools.scheduler.engine import SchedulerEngine

        engine = SchedulerEngine.create_instance()
        mock_job = MagicMock()
        engine._scheduler = MagicMock()
        engine._scheduler.get_job.return_value = mock_job

        engine.unregister_reminder("dddd4444-4444-4444-4444-444444444444")

        engine._scheduler.get_job.assert_called_once_with(
            "reminder_dddd4444-4444-4444-4444-444444444444"
        )
        mock_job.remove.assert_called_once()


class TestSchedulerEngineLoadFromDB:
    """Loading existing tasks and reminders from DB on startup."""

    def setup_method(self):
        import radbot.tools.scheduler.engine as engine_mod

        engine_mod._instance = None

    @pytest.mark.asyncio
    async def test_start_loads_tasks_from_db(self):
        from radbot.tools.scheduler.engine import SchedulerEngine

        engine = SchedulerEngine.create_instance()
        engine._scheduler = MagicMock()

        tasks = [
            {
                "task_id": "t1",
                "cron_expression": "0 8 * * *",
                "prompt": "Morning",
                "name": "morning",
            },
            {
                "task_id": "t2",
                "cron_expression": "0 20 * * *",
                "prompt": "Evening",
                "name": "evening",
            },
        ]

        with (
            patch(
                "radbot.tools.scheduler.db.list_tasks", return_value=tasks
            ) as mock_list,
            patch("radbot.tools.reminders.db.list_reminders", return_value=[]),
            patch.object(engine, "register_job") as mock_register,
        ):
            await engine.start()

        mock_list.assert_called_once_with(enabled_only=True)
        assert mock_register.call_count == 2
        mock_register.assert_any_call(tasks[0])
        mock_register.assert_any_call(tasks[1])

    @pytest.mark.asyncio
    async def test_start_loads_pending_reminders(self):
        from radbot.tools.scheduler.engine import SchedulerEngine

        engine = SchedulerEngine.create_instance()
        engine._scheduler = MagicMock()

        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        reminders = [
            {
                "reminder_id": "r1",
                "message": "Future reminder",
                "remind_at": future_time,
            },
        ]

        with (
            patch("radbot.tools.scheduler.db.list_tasks", return_value=[]),
            patch("radbot.tools.reminders.db.list_reminders", return_value=reminders),
            patch.object(engine, "register_reminder") as mock_register,
        ):
            await engine.start()

        mock_register.assert_called_once_with(reminders[0])

    @pytest.mark.asyncio
    async def test_start_marks_past_due_reminders_completed(self):
        from radbot.tools.scheduler.engine import SchedulerEngine

        engine = SchedulerEngine.create_instance()
        engine._scheduler = MagicMock()

        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        reminders = [
            {
                "reminder_id": "r-past",
                "message": "Past due reminder",
                "remind_at": past_time,
            },
        ]

        with (
            patch("radbot.tools.scheduler.db.list_tasks", return_value=[]),
            patch("radbot.tools.reminders.db.list_reminders", return_value=reminders),
            patch("radbot.tools.reminders.db.mark_completed") as mock_mark,
            patch.object(engine, "register_reminder") as mock_register,
        ):
            await engine.start()

        mock_mark.assert_called_once_with("r-past")
        mock_register.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_handles_naive_remind_at(self):
        """Naive datetimes should be treated as UTC for past-due comparison."""
        from radbot.tools.scheduler.engine import SchedulerEngine

        engine = SchedulerEngine.create_instance()
        engine._scheduler = MagicMock()

        # Naive datetime in the future (relative to UTC)
        future_naive = datetime.utcnow() + timedelta(hours=2)
        future_naive = future_naive.replace(tzinfo=None)  # ensure naive
        reminders = [
            {
                "reminder_id": "r-naive",
                "message": "Naive tz",
                "remind_at": future_naive,
            },
        ]

        with (
            patch("radbot.tools.scheduler.db.list_tasks", return_value=[]),
            patch("radbot.tools.reminders.db.list_reminders", return_value=reminders),
            patch.object(engine, "register_reminder") as mock_register,
        ):
            await engine.start()

        # Should be registered since it's in the future
        mock_register.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_handles_db_error_gracefully(self):
        """DB errors during startup should be caught, not crash."""
        from radbot.tools.scheduler.engine import SchedulerEngine

        engine = SchedulerEngine.create_instance()
        engine._scheduler = MagicMock()

        with (
            patch(
                "radbot.tools.scheduler.db.list_tasks", side_effect=Exception("DB down")
            ),
            patch(
                "radbot.tools.reminders.db.list_reminders",
                side_effect=Exception("DB down"),
            ),
        ):
            await engine.start()

        # Should still start even if DB fails
        assert engine._started is True
        engine._scheduler.start.assert_called_once()


class TestSchedulerEngineGetNextRunTime:
    """get_next_run_time returns correct values."""

    def setup_method(self):
        import radbot.tools.scheduler.engine as engine_mod

        engine_mod._instance = None

    def test_returns_next_run_time_when_job_exists(self):
        from radbot.tools.scheduler.engine import SchedulerEngine

        engine = SchedulerEngine.create_instance()
        expected_time = datetime(2030, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
        mock_job = MagicMock()
        mock_job.next_run_time = expected_time
        engine._scheduler = MagicMock()
        engine._scheduler.get_job.return_value = mock_job

        result = engine.get_next_run_time("task-123")

        assert result == expected_time

    def test_returns_none_when_no_job(self):
        from radbot.tools.scheduler.engine import SchedulerEngine

        engine = SchedulerEngine.create_instance()
        engine._scheduler = MagicMock()
        engine._scheduler.get_job.return_value = None

        result = engine.get_next_run_time("nonexistent")

        assert result is None


class TestSchedulerEngineInject:
    """Dependency injection."""

    def setup_method(self):
        import radbot.tools.scheduler.engine as engine_mod

        engine_mod._instance = None

    def test_inject_sets_managers(self):
        from radbot.tools.scheduler.engine import SchedulerEngine

        engine = SchedulerEngine.create_instance()
        cm = MagicMock()
        sm = MagicMock()

        engine.inject(cm, sm)

        assert engine._connection_manager is cm
        assert engine._session_manager is sm


# ---------------------------------------------------------------------------
# Reminder tool tests
# ---------------------------------------------------------------------------


class TestCreateReminder:
    """create_reminder tool function."""

    @patch("radbot.tools.reminders.reminder_tools.reminder_db")
    @patch(
        "radbot.tools.scheduler.engine.SchedulerEngine.get_instance", return_value=None
    )
    def test_create_with_delay_minutes(self, mock_engine, mock_db):
        from radbot.tools.reminders.reminder_tools import create_reminder

        fake_id = uuid.uuid4()
        remind_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        mock_db.create_reminder.return_value = {
            "reminder_id": fake_id,
            "message": "Test reminder",
            "remind_at": remind_at,
        }

        result = create_reminder(message="Test reminder", delay_minutes=5)

        assert result["status"] == "success"
        assert result["reminder_id"] == str(fake_id)
        assert result["message"] == "Test reminder"
        mock_db.create_reminder.assert_called_once()
        call_kwargs = mock_db.create_reminder.call_args
        assert call_kwargs.kwargs["message"] == "Test reminder"

    @patch("radbot.tools.reminders.reminder_tools.reminder_db")
    @patch(
        "radbot.tools.scheduler.engine.SchedulerEngine.get_instance", return_value=None
    )
    def test_create_with_remind_at_iso(self, mock_engine, mock_db):
        from radbot.tools.reminders.reminder_tools import create_reminder

        fake_id = uuid.uuid4()
        future_iso = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        mock_db.create_reminder.return_value = {
            "reminder_id": fake_id,
            "message": "Tomorrow thing",
            "remind_at": datetime.fromisoformat(future_iso),
        }

        result = create_reminder(message="Tomorrow thing", remind_at=future_iso)

        assert result["status"] == "success"
        assert result["reminder_id"] == str(fake_id)

    @patch("radbot.tools.reminders.reminder_tools.reminder_db")
    def test_create_rejects_past_date(self, mock_db):
        from radbot.tools.reminders.reminder_tools import create_reminder

        past_iso = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

        result = create_reminder(message="Past reminder", remind_at=past_iso)

        assert result["status"] == "error"
        assert "past" in result["message"].lower()
        mock_db.create_reminder.assert_not_called()

    @patch("radbot.tools.reminders.reminder_tools.reminder_db")
    def test_create_rejects_empty_params(self, mock_db):
        from radbot.tools.reminders.reminder_tools import create_reminder

        result = create_reminder(message="No time specified")

        assert result["status"] == "error"
        assert (
            "remind_at" in result["message"].lower()
            or "delay_minutes" in result["message"].lower()
        )
        mock_db.create_reminder.assert_not_called()

    @patch("radbot.tools.reminders.reminder_tools.reminder_db")
    def test_create_rejects_invalid_iso_format(self, mock_db):
        from radbot.tools.reminders.reminder_tools import create_reminder

        result = create_reminder(message="Bad format", remind_at="not-a-date")

        assert result["status"] == "error"
        assert "invalid" in result["message"].lower()

    @patch("radbot.tools.reminders.reminder_tools.reminder_db")
    @patch(
        "radbot.tools.scheduler.engine.SchedulerEngine.get_instance", return_value=None
    )
    def test_create_with_timezone_handling(self, mock_engine, mock_db):
        from radbot.tools.reminders.reminder_tools import create_reminder

        fake_id = uuid.uuid4()
        # Naive datetime string (no offset) — should apply timezone_name
        future_naive = (datetime.now() + timedelta(days=1)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        mock_db.create_reminder.return_value = {
            "reminder_id": fake_id,
            "message": "TZ test",
            "remind_at": datetime.now(timezone.utc) + timedelta(days=1),
        }

        result = create_reminder(
            message="TZ test",
            remind_at=future_naive,
            timezone_name="Europe/Amsterdam",
        )

        assert result["status"] == "success"
        # Verify the db was called with a timezone-aware datetime
        call_args = mock_db.create_reminder.call_args
        dt_arg = call_args.kwargs["remind_at"]
        assert dt_arg.tzinfo is not None

    @patch("radbot.tools.reminders.reminder_tools.reminder_db")
    def test_create_rejects_invalid_timezone(self, mock_db):
        from radbot.tools.reminders.reminder_tools import create_reminder

        future_naive = (datetime.now() + timedelta(days=1)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )

        result = create_reminder(
            message="Bad tz",
            remind_at=future_naive,
            timezone_name="Fake/Timezone",
        )

        assert result["status"] == "error"
        assert "timezone" in result["message"].lower()

    @patch("radbot.tools.reminders.reminder_tools.reminder_db")
    @patch("radbot.tools.scheduler.engine.SchedulerEngine.get_instance")
    def test_create_registers_with_engine(self, mock_get_instance, mock_db):
        from radbot.tools.reminders.reminder_tools import create_reminder

        fake_id = uuid.uuid4()
        remind_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        row = {
            "reminder_id": fake_id,
            "message": "Engine test",
            "remind_at": remind_at,
        }
        mock_db.create_reminder.return_value = row

        mock_engine = MagicMock()
        mock_get_instance.return_value = mock_engine

        result = create_reminder(message="Engine test", delay_minutes=10)

        assert result["status"] == "success"
        mock_engine.register_reminder.assert_called_once_with(row)


class TestListReminders:
    """list_reminders tool function."""

    @patch("radbot.tools.reminders.reminder_tools.reminder_db")
    def test_list_reminders_pending(self, mock_db):
        from radbot.tools.reminders.reminder_tools import list_reminders

        mock_db.list_reminders.return_value = [
            {
                "reminder_id": uuid.uuid4(),
                "message": "Test 1",
                "remind_at": datetime.now(timezone.utc),
                "status": "pending",
            },
        ]

        result = list_reminders(status="pending")

        assert result["status"] == "success"
        assert len(result["reminders"]) == 1
        mock_db.list_reminders.assert_called_once_with(status="pending")

    @patch("radbot.tools.reminders.reminder_tools.reminder_db")
    def test_list_reminders_all(self, mock_db):
        from radbot.tools.reminders.reminder_tools import list_reminders

        mock_db.list_reminders.return_value = []

        result = list_reminders(status="all")

        assert result["status"] == "success"
        mock_db.list_reminders.assert_called_once_with(status=None)

    @patch("radbot.tools.reminders.reminder_tools.reminder_db")
    def test_list_reminders_handles_error(self, mock_db):
        from radbot.tools.reminders.reminder_tools import list_reminders

        mock_db.list_reminders.side_effect = Exception("DB error")

        result = list_reminders()

        assert result["status"] == "error"
        assert "failed" in result["message"].lower()


class TestDeleteReminder:
    """delete_reminder tool function."""

    @patch("radbot.tools.reminders.reminder_tools.reminder_db")
    @patch(
        "radbot.tools.scheduler.engine.SchedulerEngine.get_instance", return_value=None
    )
    def test_delete_existing_reminder(self, mock_engine, mock_db):
        from radbot.tools.reminders.reminder_tools import delete_reminder

        rid = str(uuid.uuid4())
        mock_db.delete_reminder.return_value = True

        result = delete_reminder(reminder_id=rid)

        assert result["status"] == "success"
        assert result["reminder_id"] == rid

    @patch("radbot.tools.reminders.reminder_tools.reminder_db")
    @patch(
        "radbot.tools.scheduler.engine.SchedulerEngine.get_instance", return_value=None
    )
    def test_delete_nonexistent_reminder(self, mock_engine, mock_db):
        from radbot.tools.reminders.reminder_tools import delete_reminder

        rid = str(uuid.uuid4())
        mock_db.delete_reminder.return_value = False

        result = delete_reminder(reminder_id=rid)

        assert result["status"] == "error"
        assert "not found" in result["message"].lower()

    def test_delete_invalid_uuid(self):
        from radbot.tools.reminders.reminder_tools import delete_reminder

        result = delete_reminder(reminder_id="not-a-uuid")

        assert result["status"] == "error"
        assert "uuid" in result["message"].lower()

    @patch("radbot.tools.reminders.reminder_tools.reminder_db")
    @patch("radbot.tools.scheduler.engine.SchedulerEngine.get_instance")
    def test_delete_unregisters_from_engine(self, mock_get_instance, mock_db):
        from radbot.tools.reminders.reminder_tools import delete_reminder

        rid = str(uuid.uuid4())
        mock_db.delete_reminder.return_value = True

        mock_engine = MagicMock()
        mock_get_instance.return_value = mock_engine

        result = delete_reminder(reminder_id=rid)

        assert result["status"] == "success"
        mock_engine.unregister_reminder.assert_called_once_with(rid)
