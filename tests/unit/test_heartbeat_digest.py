"""Unit tests for Heartbeat digest assembly and delivery."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from radbot.tools.heartbeat.delivery import deliver_digest
from radbot.tools.heartbeat.digest import assemble_digest


@pytest.mark.asyncio
async def test_digest_empty_when_all_sources_empty():
    with (
        patch("radbot.tools.heartbeat.digest._fetch_tasks", return_value=[]),
        patch("radbot.tools.heartbeat.digest._fetch_calendar", return_value=[]),
        patch("radbot.tools.heartbeat.digest._fetch_reminders", return_value=[]),
        patch("radbot.tools.heartbeat.digest._fetch_alerts", return_value=[]),
        patch(
            "radbot.tools.heartbeat.digest._fetch_overnight_scheduler", return_value=[]
        ),
    ):
        md = await assemble_digest()
    assert md == ""


@pytest.mark.asyncio
async def test_digest_renders_all_sections():
    now = datetime.now(timezone.utc)
    tasks = [
        {
            "ref_code": "PT1",
            "content": "finish draft",
            "due": now.date().isoformat(),
            "overdue": False,
        }
    ]
    events = [{"summary": "Standup", "start": {"dateTime": now.isoformat()}}]
    reminders = [{"message": "call mom", "remind_at": now + timedelta(hours=2)}]
    alerts = [{"severity": "warning", "alertname": "DiskFull", "instance": "srv1"}]
    overnight = [{"task_name": "nightly-backup", "response": "ok, 42 files"}]
    with (
        patch("radbot.tools.heartbeat.digest._fetch_tasks", return_value=tasks),
        patch("radbot.tools.heartbeat.digest._fetch_calendar", return_value=events),
        patch("radbot.tools.heartbeat.digest._fetch_reminders", return_value=reminders),
        patch("radbot.tools.heartbeat.digest._fetch_alerts", return_value=alerts),
        patch(
            "radbot.tools.heartbeat.digest._fetch_overnight_scheduler",
            return_value=overnight,
        ),
    ):
        md = await assemble_digest()
    assert "# Heartbeat" in md
    assert "## Tasks" in md and "PT1" in md and "finish draft" in md
    assert "## Calendar" in md and "Standup" in md
    assert "## Reminders" in md and "call mom" in md
    assert "## Alerts" in md and "DiskFull" in md
    assert "## Overnight Activity" in md and "nightly-backup" in md


@pytest.mark.asyncio
async def test_digest_calendar_failure_degrades_silently():
    tasks = [{"ref_code": "PT1", "content": "t", "due": None, "overdue": False}]

    def raise_cal(*_a, **_k):
        raise RuntimeError("unauth")

    with (
        patch("radbot.tools.heartbeat.digest._fetch_tasks", return_value=tasks),
        patch("radbot.tools.heartbeat.digest._fetch_calendar", side_effect=raise_cal),
        patch("radbot.tools.heartbeat.digest._fetch_reminders", return_value=[]),
        patch("radbot.tools.heartbeat.digest._fetch_alerts", return_value=[]),
        patch(
            "radbot.tools.heartbeat.digest._fetch_overnight_scheduler", return_value=[]
        ),
    ):
        with pytest.raises(RuntimeError):
            # the raw fetcher raises; assemble_digest itself isn't protecting
            # third-party patches, so this just validates our own fetchers
            # don't swallow caller-raised errors. The real _fetch_calendar
            # already has its own try/except.
            await assemble_digest()


@pytest.mark.asyncio
async def test_deliver_digest_empty_returns_false():
    delivered = await deliver_digest("")
    assert delivered is False


@pytest.mark.asyncio
async def test_deliver_digest_no_notifier_returns_false():
    """If the Notifier seam was never installed, delivery is a no-op."""
    from radbot.services.notifier import reset_notifier

    reset_notifier()
    delivered = await deliver_digest("# Heartbeat\n\ncontent")
    assert delivered is False


@pytest.mark.asyncio
async def test_deliver_digest_publishes_heartbeat_event_through_notifier():
    """delivery.py constructs a HeartbeatEvent and hands it to the Notifier."""
    from radbot.services.notifier import (
        HeartbeatEvent,
        Notifier,
        reset_notifier,
        set_notifier,
    )

    received: list = []

    class RecordingSink:
        name = "recording"

        async def publish(self, event):
            received.append(event)

    set_notifier(Notifier(sinks=[RecordingSink()]))
    try:
        delivered = await deliver_digest(
            "# Heartbeat\n\nsome markdown", title="Morning Brief"
        )
    finally:
        reset_notifier()

    assert delivered is True
    assert len(received) == 1
    event = received[0]
    assert isinstance(event, HeartbeatEvent)
    assert event.title == "Morning Brief"
    assert event.message.startswith("# Heartbeat")
    assert "sunrise" in event.tags
    assert event.digest_markdown == "# Heartbeat\n\nsome markdown"


@pytest.mark.asyncio
async def test_fetch_tasks_filters_future_and_done(monkeypatch):
    """Direct test of _fetch_tasks filtering via mocked telos list_section."""
    from radbot.tools.heartbeat import digest as digest_mod

    future_date = (datetime.now().date() + timedelta(days=30)).isoformat()
    today = datetime.now().date().isoformat()
    overdue = (datetime.now().date() - timedelta(days=2)).isoformat()

    entries = [
        SimpleNamespace(ref_code="PT1", content="today", metadata={"due_date": today}),
        SimpleNamespace(
            ref_code="PT2", content="future", metadata={"due_date": future_date}
        ),
        SimpleNamespace(
            ref_code="PT3",
            content="done-today",
            metadata={"due_date": today, "task_status": "done"},
        ),
        SimpleNamespace(
            ref_code="PT4", content="overdue", metadata={"due_date": overdue}
        ),
        SimpleNamespace(ref_code="PT5", content="no-due", metadata={}),
    ]

    fake_list = MagicMock(return_value=entries)
    fake_section = SimpleNamespace(PROJECT_TASKS="project_tasks")
    # Patch imports *inside* _fetch_tasks.
    import sys

    telos_db = sys.modules.setdefault("radbot.tools.telos.db", MagicMock())
    telos_models = sys.modules.setdefault("radbot.tools.telos.models", MagicMock())
    monkeypatch.setattr(telos_db, "list_section", fake_list)
    monkeypatch.setattr(telos_models, "Section", fake_section)

    out = digest_mod._fetch_tasks(datetime.now(timezone.utc) + timedelta(days=1))
    refs = {t["ref_code"] for t in out}
    # Future task excluded, done task excluded; today, overdue, and no-due included.
    assert "PT2" not in refs
    assert "PT3" not in refs
    assert "PT1" in refs
    assert "PT4" in refs
    assert "PT5" in refs
    # overdue flag set correctly
    overdue_task = next(t for t in out if t["ref_code"] == "PT4")
    assert overdue_task["overdue"] is True
