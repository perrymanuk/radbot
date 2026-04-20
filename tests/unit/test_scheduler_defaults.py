"""Unit tests for scheduler default proactive primitives registration."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from radbot.tools.scheduler.defaults import (
    DEFAULT_DISTILLER_CRON,
    DEFAULT_DREAM_CRON,
    DEFAULT_HEARTBEAT_CRON,
    DISTILLER_JOB_ID,
    DREAM_JOB_ID,
    HEARTBEAT_JOB_ID,
    register_default_jobs,
)


def _engine_with_scheduler():
    scheduler = MagicMock()
    scheduler.get_job = MagicMock(return_value=None)
    engine = SimpleNamespace(_scheduler=scheduler)
    return engine, scheduler


def test_register_default_jobs_both_enabled_by_default():
    engine, scheduler = _engine_with_scheduler()
    with patch("radbot.tools.scheduler.defaults._get_section", return_value={}):
        register_default_jobs(engine)

    assert scheduler.add_job.call_count == 3
    ids = [call.kwargs["id"] for call in scheduler.add_job.call_args_list]
    assert DREAM_JOB_ID in ids
    assert DISTILLER_JOB_ID in ids
    assert HEARTBEAT_JOB_ID in ids


def test_register_default_jobs_both_disabled():
    engine, scheduler = _engine_with_scheduler()
    with patch(
        "radbot.tools.scheduler.defaults._get_section",
        return_value={"enabled": False},
    ):
        register_default_jobs(engine)

    scheduler.add_job.assert_not_called()


def test_register_default_jobs_uses_custom_cron():
    engine, scheduler = _engine_with_scheduler()
    custom = "*/15 * * * *"

    def section(name):
        return {"enabled": True, "cron_expression": custom}

    with patch("radbot.tools.scheduler.defaults._get_section", side_effect=section):
        register_default_jobs(engine)

    # All three jobs added with the custom cron expression — we don't
    # inspect the trigger object directly, but we verify count.
    assert scheduler.add_job.call_count == 3


def test_register_default_jobs_bad_cron_is_logged_and_skipped():
    engine, scheduler = _engine_with_scheduler()

    def section(name):
        if name == "dream":
            return {"enabled": True, "cron_expression": "not a cron"}
        return {"enabled": True}  # distiller + heartbeat use defaults

    with patch("radbot.tools.scheduler.defaults._get_section", side_effect=section):
        register_default_jobs(engine)

    # Only distiller + heartbeat should have been added (dream has bad cron).
    assert scheduler.add_job.call_count == 2
    ids = [call.kwargs["id"] for call in scheduler.add_job.call_args_list]
    assert DISTILLER_JOB_ID in ids
    assert HEARTBEAT_JOB_ID in ids
    assert DREAM_JOB_ID not in ids


def test_register_default_jobs_replaces_existing():
    engine, scheduler = _engine_with_scheduler()
    existing = MagicMock()
    # Return an existing job only for dream.

    def get_job(job_id):
        return existing if job_id == DREAM_JOB_ID else None

    scheduler.get_job.side_effect = get_job

    with patch("radbot.tools.scheduler.defaults._get_section", return_value={}):
        register_default_jobs(engine)

    existing.remove.assert_called_once()
    assert scheduler.add_job.call_count == 3


def test_register_default_jobs_handles_missing_scheduler():
    # No exception even if engine has no _scheduler.
    engine = SimpleNamespace(_scheduler=None)
    with patch("radbot.tools.scheduler.defaults._get_section", return_value={}):
        register_default_jobs(engine)  # no-op, must not raise


def test_defaults_constants_are_valid_5_field_cron():
    for expr in (DEFAULT_DREAM_CRON, DEFAULT_DISTILLER_CRON, DEFAULT_HEARTBEAT_CRON):
        assert len(expr.split()) == 5
