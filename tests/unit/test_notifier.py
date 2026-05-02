"""Unit tests for the Notifier service (PR1 of EX41).

Covers:
- The fan-out semantics (publishes to all configured sinks)
- Per-event sink-skip via `skip_sinks`
- Self-skipping by sinks based on event type / flags
- Fail-soft semantics (one sink failing does not block the others)
- Per-sink timeout via asyncio.wait_for
- Pydantic WS payload validation

The tests use an in-memory `RecordingSink` fake so we can assert on dispatched
events without booting WS / DB / ntfy.
"""

import asyncio
from typing import List

import pytest

from radbot.services.notifier import (
    AlertEvent,
    ChatHistorySink,
    HeartbeatEvent,
    NotificationsTableSink,
    Notifier,
    NtfySink,
    ReminderEvent,
    ResultEvent,
    ScheduledTaskEvent,
    WebhookEvent,
    WebSocketChatSink,
    WsNotificationPayload,
    WsSystemMessagePayload,
    build_default_notifier,
    get_notifier,
    reset_notifier,
    set_notifier,
)

# ---------------------------------------------------------------------------
# Test fakes
# ---------------------------------------------------------------------------


class RecordingSink:
    """In-memory `NotificationSink` that records every event it receives."""

    def __init__(self, name: str = "recording") -> None:
        self.name = name
        self.events: List[ResultEvent] = []

    async def publish(self, event: ResultEvent) -> None:
        self.events.append(event)


class FailingSink:
    name = "failing"

    async def publish(self, event: ResultEvent) -> None:
        raise RuntimeError("simulated sink failure")


class HangingSink:
    name = "hanging"

    async def publish(self, event: ResultEvent) -> None:
        await asyncio.sleep(60)  # well beyond the test's wait_for timeout


# ---------------------------------------------------------------------------
# Notifier.publish — fan-out + skip + fail-soft + timeout
# ---------------------------------------------------------------------------


class TestNotifierPublishesToAllConfiguredSinks:
    @pytest.mark.asyncio
    async def test_publishes_to_every_sink(self) -> None:
        a = RecordingSink("a")
        b = RecordingSink("b")
        c = RecordingSink("c")
        notifier = Notifier(sinks=[a, b, c])

        event = ScheduledTaskEvent(
            title="t", message="m", task_id="x", task_name="n", session_id="s"
        )
        await notifier.publish(event)

        assert a.events == [event]
        assert b.events == [event]
        assert c.events == [event]

    @pytest.mark.asyncio
    async def test_publish_returns_none(self) -> None:
        notifier = Notifier(sinks=[RecordingSink()])
        result = await notifier.publish(
            ResultEvent(title="t", message="m"),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_publish_with_no_sinks_is_noop(self) -> None:
        notifier = Notifier(sinks=[])
        await notifier.publish(ResultEvent(title="t", message="m"))


class TestNotifierSkipSinks:
    @pytest.mark.asyncio
    async def test_skip_sinks_excludes_named_sinks(self) -> None:
        a = RecordingSink("a")
        b = RecordingSink("b")
        c = RecordingSink("c")
        notifier = Notifier(sinks=[a, b, c])

        event = ReminderEvent(
            title="r",
            message="late delivery",
            reminder_id="rid",
            session_id="sid",
            deliver_to_chat=True,
            skip_sinks=frozenset({"b"}),
        )
        await notifier.publish(event)

        assert a.events == [event]
        assert b.events == []
        assert c.events == [event]


class TestNotifierFailSoft:
    @pytest.mark.asyncio
    async def test_one_failing_sink_does_not_block_others(self) -> None:
        good = RecordingSink("good")
        notifier = Notifier(sinks=[FailingSink(), good])

        await notifier.publish(ResultEvent(title="t", message="m"))

        assert len(good.events) == 1


class TestNotifierTimeout:
    @pytest.mark.asyncio
    async def test_hanging_sink_is_bounded_by_timeout(self) -> None:
        good = RecordingSink("good")
        notifier = Notifier(sinks=[HangingSink(), good], sink_timeout=0.05)

        # Should return well before HangingSink's 60s sleep.
        await asyncio.wait_for(
            notifier.publish(ResultEvent(title="t", message="m")),
            timeout=2.0,
        )
        # Good sink still received the event despite the hanging sibling.
        assert len(good.events) == 1


# ---------------------------------------------------------------------------
# ChatHistorySink — self-skipping by event type/flags
# ---------------------------------------------------------------------------


class TestChatHistorySink:
    @pytest.mark.asyncio
    async def test_persists_scheduled_task_response(self) -> None:
        calls: List[tuple] = []

        def fake_add(session_id, role, content, user_id=None, **kwargs):
            calls.append((session_id, role, content, user_id))

        sink = ChatHistorySink(add_message=fake_add)

        await sink.publish(
            ScheduledTaskEvent(
                title="t",
                message="ignored",
                task_id="tid",
                task_name="n",
                session_id="sess",
                response="hello world",
            )
        )

        assert calls == [("sess", "assistant", "hello world", "web_user")]

    @pytest.mark.asyncio
    async def test_scheduled_task_with_empty_response_is_noop(self) -> None:
        calls: List[tuple] = []
        sink = ChatHistorySink(add_message=lambda *a, **k: calls.append((a, k)))

        await sink.publish(
            ScheduledTaskEvent(
                title="t",
                message="m",
                task_id="tid",
                task_name="n",
                session_id="sess",
                response="",
            )
        )

        assert calls == []

    @pytest.mark.asyncio
    async def test_reminder_self_skips_when_deliver_to_chat_false(self) -> None:
        calls: List[tuple] = []
        sink = ChatHistorySink(add_message=lambda *a, **k: calls.append((a, k)))

        await sink.publish(
            ReminderEvent(
                title="r",
                message="m",
                reminder_id="rid",
                session_id="sess",
                deliver_to_chat=False,
            )
        )

        assert calls == []

    @pytest.mark.asyncio
    async def test_reminder_persists_system_message_when_delivered(self) -> None:
        calls: List[tuple] = []

        def fake_add(session_id, role, content, user_id=None, **kwargs):
            calls.append((session_id, role, content, user_id))

        sink = ChatHistorySink(add_message=fake_add)

        await sink.publish(
            ReminderEvent(
                title="r",
                message="walk the dog",
                reminder_id="rid",
                session_id="sess",
                deliver_to_chat=True,
            )
        )

        assert calls == [("sess", "system", "[Reminder] walk the dog", "web_user")]


# ---------------------------------------------------------------------------
# NtfySink — degrades gracefully when ntfy is unconfigured
# ---------------------------------------------------------------------------


class TestNtfySink:
    @pytest.mark.asyncio
    async def test_unconfigured_ntfy_is_noop(self) -> None:
        sink = NtfySink(client_getter=lambda: None)
        # Should not raise even though no client exists
        await sink.publish(
            ScheduledTaskEvent(title="t", message="m", task_id="x", task_name="n"),
        )

    @pytest.mark.asyncio
    async def test_publishes_through_client_getter(self) -> None:
        captured: dict = {}

        class FakeClient:
            async def publish(self, **kwargs):
                captured.update(kwargs)
                return {"ok": True}

        sink = NtfySink(client_getter=lambda: FakeClient())

        await sink.publish(
            ReminderEvent(
                title="Reminder",
                message="Take meds",
                reminder_id="rid",
                tags="bell",
                priority="high",
            )
        )

        assert captured["title"] == "Reminder"
        assert captured["message"] == "Take meds"
        assert captured["tags"] == "bell"
        assert captured["priority"] == "high"
        # skip_notification flag was removed in EX41 PR3 — the Notifier owns
        # the notifications-table fan-out now, so ntfy_client.publish() no
        # longer accepts it.
        assert "skip_notification" not in captured


# ---------------------------------------------------------------------------
# NotificationsTableSink — writes row + broadcasts badge
# ---------------------------------------------------------------------------


class TestNotificationsTableSink:
    @pytest.mark.asyncio
    async def test_writes_scheduled_task_row_and_broadcasts_badge(self) -> None:
        captured_create: dict = {}
        captured_broadcast: List[dict] = []

        def fake_create(**kwargs) -> dict:
            captured_create.update(kwargs)
            return {"notification_id": "n123"}

        async def fake_broadcast(payload: dict) -> None:
            captured_broadcast.append(payload)

        sink = NotificationsTableSink(
            ws_broadcaster=fake_broadcast,
            create_notification=fake_create,
        )

        await sink.publish(
            ScheduledTaskEvent(
                title="Scheduled: foo",
                message="result body",
                task_id="tid",
                task_name="foo",
                session_id="sess",
                prompt="do the thing",
            )
        )

        assert captured_create["type"] == "scheduled_task"
        assert captured_create["source_id"] == "tid"
        assert captured_create["session_id"] == "sess"
        assert captured_create["metadata"]["task_name"] == "foo"
        assert captured_broadcast == [
            {
                "type": "notification",
                "content": {
                    "notification_id": "n123",
                    "notification_type": "scheduled_task",
                    "title": "Scheduled: foo",
                },
            }
        ]

    @pytest.mark.asyncio
    async def test_writes_reminder_row(self) -> None:
        captured_create: dict = {}

        def fake_create(**kwargs) -> dict:
            captured_create.update(kwargs)
            return {"notification_id": "rmid"}

        sink = NotificationsTableSink(
            ws_broadcaster=None, create_notification=fake_create
        )

        await sink.publish(
            ReminderEvent(
                title="Reminder",
                message="Walk the dog",
                reminder_id="rid",
                deliver_to_chat=False,
            )
        )

        assert captured_create["type"] == "reminder"
        assert captured_create["source_id"] == "rid"
        assert captured_create["metadata"] == {"reminder_id": "rid"}


# ---------------------------------------------------------------------------
# WebSocketChatSink — only fires for delivered reminders
# ---------------------------------------------------------------------------


class TestWebSocketChatSink:
    @pytest.mark.asyncio
    async def test_skips_undelivered_reminder(self) -> None:
        broadcasts: List[dict] = []
        sink = WebSocketChatSink(ws_broadcaster=lambda p: _record(broadcasts, p))

        await sink.publish(
            ReminderEvent(
                title="r",
                message="m",
                reminder_id="rid",
                deliver_to_chat=False,
            )
        )

        assert broadcasts == []

    @pytest.mark.asyncio
    async def test_broadcasts_system_message_for_delivered_reminder(self) -> None:
        broadcasts: List[dict] = []
        sink = WebSocketChatSink(ws_broadcaster=lambda p: _record(broadcasts, p))

        await sink.publish(
            ReminderEvent(
                title="r",
                message="walk the dog",
                reminder_id="rid",
                session_id="sess",
                deliver_to_chat=True,
            )
        )

        assert broadcasts == [
            {
                "type": "message",
                "role": "system",
                "content": "[Reminder] walk the dog",
            }
        ]

    @pytest.mark.asyncio
    async def test_skips_scheduled_task_event(self) -> None:
        broadcasts: List[dict] = []
        sink = WebSocketChatSink(ws_broadcaster=lambda p: _record(broadcasts, p))

        await sink.publish(
            ScheduledTaskEvent(
                title="t",
                message="m",
                task_id="x",
                task_name="n",
                session_id="s",
                response="r",
            )
        )

        assert broadcasts == []


# ---------------------------------------------------------------------------
# Pydantic WS payload schemas
# ---------------------------------------------------------------------------


class TestWsPayloadSchemas:
    def test_notification_payload_serialises_with_constant_type(self) -> None:
        p = WsNotificationPayload.model_validate(
            {
                "content": {
                    "notification_id": "n",
                    "notification_type": "reminder",
                    "title": "Reminder",
                }
            }
        )
        assert p.model_dump() == {
            "type": "notification",
            "content": {
                "notification_id": "n",
                "notification_type": "reminder",
                "title": "Reminder",
            },
        }

    def test_system_message_payload_serialises_with_constant_role(self) -> None:
        p = WsSystemMessagePayload(content="hi")
        assert p.model_dump() == {
            "type": "message",
            "role": "system",
            "content": "hi",
        }

    def test_invalid_notification_payload_rejected(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            WsNotificationPayload.model_validate(
                {"content": {"notification_id": 1}}  # missing required fields
            )


# ---------------------------------------------------------------------------
# Module-level singleton accessor
# ---------------------------------------------------------------------------


class TestSingletonAccessor:
    def setup_method(self) -> None:
        reset_notifier()

    def teardown_method(self) -> None:
        reset_notifier()

    def test_get_notifier_returns_none_when_unset(self) -> None:
        assert get_notifier() is None

    def test_set_then_get(self) -> None:
        n = Notifier(sinks=[])
        set_notifier(n)
        assert get_notifier() is n

    def test_reset_clears(self) -> None:
        set_notifier(Notifier(sinks=[]))
        reset_notifier()
        assert get_notifier() is None

    def test_build_default_notifier_creates_canonical_sinks(self) -> None:
        async def fake_broadcast(_payload: dict) -> None:
            return None

        n = build_default_notifier(ws_broadcaster=fake_broadcast)
        names = sorted(s.name for s in n.sinks)
        assert names == ["chat_history", "notifications", "ntfy", "ws_chat"]


# ---------------------------------------------------------------------------
# AlertEvent / HeartbeatEvent — sink-side phase inspection (EX42)
# ---------------------------------------------------------------------------


class TestChatHistorySinkSkipsNonChatEvents:
    """ChatHistorySink must inspect event type and skip alerts + heartbeats."""

    @pytest.mark.asyncio
    async def test_skips_alert_event(self) -> None:
        calls: List[tuple] = []
        sink = ChatHistorySink(add_message=lambda *a, **k: calls.append((a, k)))

        await sink.publish(
            AlertEvent(
                title="Investigating: x",
                message="m",
                phase="investigating",
                alertname="x",
            )
        )

        assert calls == []

    @pytest.mark.asyncio
    async def test_skips_heartbeat_event(self) -> None:
        calls: List[tuple] = []
        sink = ChatHistorySink(add_message=lambda *a, **k: calls.append((a, k)))

        await sink.publish(
            HeartbeatEvent(title="Heartbeat", message="digest"),
        )

        assert calls == []


class TestNotificationsTableSinkInspectsAlertPhase:
    """Only AlertEvent(phase='received') should produce a notifications row."""

    @pytest.mark.asyncio
    async def test_inserts_row_on_received_phase(self) -> None:
        captured: dict = {}

        def fake_create(**kwargs) -> dict:
            captured.update(kwargs)
            return {"notification_id": "abc"}

        sink = NotificationsTableSink(
            ws_broadcaster=None, create_notification=fake_create
        )

        await sink.publish(
            AlertEvent(
                title="Alert Received: HighCPU",
                message="severity: warning",
                phase="received",
                alert_id="a-1",
                alertname="HighCPU",
                severity="warning",
                instance="srv1",
            )
        )

        assert captured["type"] == "alert"
        assert captured["source_id"] == "a-1"
        assert captured["metadata"]["alertname"] == "HighCPU"
        assert captured["metadata"]["severity"] == "warning"

    @pytest.mark.parametrize("phase", ["investigating", "resolved", "failed"])
    @pytest.mark.asyncio
    async def test_skips_non_received_phases(self, phase: str) -> None:
        calls: List[dict] = []

        def fake_create(**kwargs) -> dict:
            calls.append(kwargs)
            return {"notification_id": "x"}

        sink = NotificationsTableSink(
            ws_broadcaster=None, create_notification=fake_create
        )

        await sink.publish(
            AlertEvent(
                title="x",
                message="y",
                phase=phase,  # type: ignore[arg-type]
                alertname="HighCPU",
            )
        )

        assert calls == []

    @pytest.mark.asyncio
    async def test_inserts_row_for_heartbeat_event(self) -> None:
        captured: dict = {}

        def fake_create(**kwargs) -> dict:
            captured.update(kwargs)
            return {"notification_id": "h-1"}

        sink = NotificationsTableSink(
            ws_broadcaster=None, create_notification=fake_create
        )

        await sink.publish(HeartbeatEvent(title="Heartbeat", message="digest body"))

        assert captured["type"] == "heartbeat"
        assert captured["metadata"] == {"channel": "ntfy"}


class TestWebSocketChatSinkSkipsAlertsAndHeartbeats:
    @pytest.mark.asyncio
    async def test_skips_alert_event(self) -> None:
        broadcasts: List[dict] = []
        sink = WebSocketChatSink(ws_broadcaster=lambda p: _record(broadcasts, p))

        await sink.publish(
            AlertEvent(
                title="Investigating: x",
                message="m",
                phase="investigating",
                alertname="x",
            )
        )

        assert broadcasts == []

    @pytest.mark.asyncio
    async def test_skips_heartbeat_event(self) -> None:
        broadcasts: List[dict] = []
        sink = WebSocketChatSink(ws_broadcaster=lambda p: _record(broadcasts, p))

        await sink.publish(HeartbeatEvent(title="Heartbeat", message="m"))

        assert broadcasts == []


class TestWebhookEventSinkSkips:
    """Every canonical sink should skip-with-debug for WebhookEvent today.

    Webhooks publish a WebhookEvent purely for instrumentation / future
    sinks; no current sink consumes it (the legacy `webhook_result` WS
    broadcast had no frontend consumers and was dropped in EX41 PR3).
    """

    @pytest.mark.asyncio
    async def test_chat_history_sink_skips_webhook(self) -> None:
        calls: List[tuple] = []
        sink = ChatHistorySink(add_message=lambda *a, **k: calls.append((a, k)))

        await sink.publish(
            WebhookEvent(
                title="Webhook: deploy",
                message="ok",
                webhook_id="w-1",
                webhook_name="deploy",
            )
        )

        assert calls == []

    @pytest.mark.asyncio
    async def test_ntfy_sink_skips_webhook(self) -> None:
        captured: dict = {}

        class FakeClient:
            async def publish(self, **kwargs):
                captured.update(kwargs)
                return {"ok": True}

        sink = NtfySink(client_getter=lambda: FakeClient())

        await sink.publish(
            WebhookEvent(
                title="Webhook: deploy",
                message="ok",
                webhook_id="w-1",
                webhook_name="deploy",
            )
        )

        assert captured == {}

    @pytest.mark.asyncio
    async def test_notifications_table_sink_skips_webhook(self) -> None:
        calls: List[dict] = []

        def fake_create(**kwargs) -> dict:
            calls.append(kwargs)
            return {"notification_id": "x"}

        sink = NotificationsTableSink(
            ws_broadcaster=None, create_notification=fake_create
        )

        await sink.publish(
            WebhookEvent(
                title="Webhook: deploy",
                message="ok",
                webhook_id="w-1",
                webhook_name="deploy",
            )
        )

        assert calls == []

    @pytest.mark.asyncio
    async def test_websocket_chat_sink_skips_webhook(self) -> None:
        broadcasts: List[dict] = []
        sink = WebSocketChatSink(ws_broadcaster=lambda p: _record(broadcasts, p))

        await sink.publish(
            WebhookEvent(
                title="Webhook: deploy",
                message="ok",
                webhook_id="w-1",
                webhook_name="deploy",
            )
        )

        assert broadcasts == []

    @pytest.mark.asyncio
    async def test_default_notifier_publish_is_a_noop_for_webhook(self) -> None:
        """End-to-end: a WebhookEvent through build_default_notifier hits no sink."""
        broadcasts: List[dict] = []

        async def fake_broadcast(payload: dict) -> None:
            broadcasts.append(payload)

        notifier = build_default_notifier(ws_broadcaster=fake_broadcast)

        await notifier.publish(
            WebhookEvent(
                title="Webhook: deploy",
                message="ok",
                webhook_id="w-1",
                webhook_name="deploy",
            )
        )

        assert broadcasts == []


class TestNotifierSurfacesSinkExceptionsAtErrorLevel:
    """Per PT106 #3: dropped events must be loud."""

    @pytest.mark.asyncio
    async def test_failing_sink_logs_at_error_level(self, caplog) -> None:
        notifier = Notifier(sinks=[FailingSink()])

        with caplog.at_level("ERROR", logger="radbot.services.notifier"):
            await notifier.publish(ResultEvent(title="t", message="m"))

        error_records = [r for r in caplog.records if r.levelname == "ERROR"]
        assert any(
            "Notifier sink 'failing' raised" in r.getMessage() for r in error_records
        )

    @pytest.mark.asyncio
    async def test_hanging_sink_logs_timeout_at_error_level(self, caplog) -> None:
        notifier = Notifier(sinks=[HangingSink()], sink_timeout=0.01)

        with caplog.at_level("ERROR", logger="radbot.services.notifier"):
            await notifier.publish(ResultEvent(title="t", message="m"))

        error_records = [r for r in caplog.records if r.levelname == "ERROR"]
        assert any(
            "timed out" in r.getMessage() and "hanging" in r.getMessage()
            for r in error_records
        )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _record(target: list, payload: dict) -> None:
    target.append(payload)
