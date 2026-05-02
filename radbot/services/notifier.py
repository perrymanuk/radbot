"""Notifier service — fan out a result event to all configured sinks.

Single seam owned by post-trigger result delivery. PR1 of EX41 covers the
scheduler `_execute_job` and reminder firing paths; later PRs migrate
alertmanager, heartbeat, and webhooks.

Architecture:
- Polymorphic dataclasses encode events (`ResultEvent` base + per-kind subclasses).
- Pydantic `WsPayload` models validate the WebSocket broadcast payloads so
  the frontend protocol has a single source of truth.
- `NotificationSink` is a Protocol; concrete adapters are injected via the
  `Notifier` constructor (dependency inversion — tests use an in-memory fake).
- `Notifier.publish()` fans out via `asyncio.gather(return_exceptions=True)`,
  with every sink wrapped in `asyncio.wait_for()` to bound latency. Per-sink
  failures are caught and logged; `publish()` always returns `None` so callers
  do not branch on partial success.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, FrozenSet, Literal, Optional, Protocol

from pydantic import BaseModel

logger = logging.getLogger(__name__)

Priority = Literal["min", "low", "default", "high", "max"]
DEFAULT_SINK_TIMEOUT = 10.0


# ---------------------------------------------------------------------------
# Event shapes — polymorphic dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ResultEvent:
    """Base event — every fan-out has a title, message, and priority.

    `skip_sinks` lets a caller opt a specific event out of named sinks (e.g.
    a late reminder delivery should not re-fire ntfy or rewrite the
    notifications row that the original firing already produced).
    """

    title: str
    message: str
    priority: Priority = "default"
    skip_sinks: FrozenSet[str] = field(default_factory=frozenset)


@dataclass
class ScheduledTaskEvent(ResultEvent):
    """Result of a scheduled task firing."""

    task_id: str = ""
    task_name: str = ""
    session_id: str = ""
    prompt: str = ""
    # Full assistant response (sinks truncate as needed for their medium).
    response: str = ""
    tags: str = "robot,clock"


@dataclass
class ReminderEvent(ResultEvent):
    """Result of a reminder firing.

    `deliver_to_chat` controls whether the chat-history persist + WS
    system-message broadcast engage. Live firings with active connections
    set this True; offline firings (no WS connections) leave it False so
    only ntfy + notifications-table sinks fire.
    """

    reminder_id: str = ""
    session_id: Optional[str] = None
    deliver_to_chat: bool = False
    tags: str = "bell"


AlertPhase = Literal["received", "investigating", "resolved", "failed"]


@dataclass
class AlertEvent(ResultEvent):
    """Alertmanager pipeline event.

    `phase` discriminates between moments in the remediation flow. Sinks
    inspect `phase` to decide whether to handle the event — the publisher
    does not route via `skip_sinks` for AlertEvent phases (EX42 §
    "Decoupled Routing").

    `prompt` and `response` are populated only on terminal phases
    (`resolved` / `failed` after a Claude Code remediation run) so the
    legacy `alert_result` WS payload can be reconstructed by the relevant
    sink without a separate publish call.
    """

    phase: AlertPhase = "received"
    alert_id: str = ""
    alertname: str = ""
    severity: Optional[str] = None
    instance: Optional[str] = None
    summary: str = ""
    fingerprint: str = ""
    prompt: str = ""
    response: str = ""
    tags: str = "warning,robot"


@dataclass
class HeartbeatEvent(ResultEvent):
    """Heartbeat / digest delivery event."""

    digest_markdown: str = ""
    tags: str = "sunrise,robot"


# ---------------------------------------------------------------------------
# WS payload schemas — Pydantic for output validation
# ---------------------------------------------------------------------------


class _WsNotificationContent(BaseModel):
    notification_id: str
    notification_type: str
    title: str


class WsNotificationPayload(BaseModel):
    type: Literal["notification"] = "notification"
    content: _WsNotificationContent


class WsSystemMessagePayload(BaseModel):
    type: Literal["message"] = "message"
    role: Literal["system"] = "system"
    content: str


# ---------------------------------------------------------------------------
# Sink protocol
# ---------------------------------------------------------------------------


class NotificationSink(Protocol):
    """A single fan-out destination. Implementations may raise — Notifier
    catches and logs every per-sink exception so callers don't branch on
    partial failure.
    """

    name: str

    async def publish(self, event: ResultEvent) -> None: ...


WsBroadcaster = Callable[[dict], Awaitable[Any]]


# ---------------------------------------------------------------------------
# Concrete sinks (production implementations)
# ---------------------------------------------------------------------------


class ChatHistorySink:
    """Persist event content to the chat_messages table.

    - `ScheduledTaskEvent` -> persist the assistant `response`.
    - `ReminderEvent` (with `deliver_to_chat=True`) -> persist a system-message
      line tagged "[Reminder] ...".
    """

    name = "chat_history"

    def __init__(self, add_message: Optional[Callable[..., Any]] = None) -> None:
        self._add_message = add_message

    def _resolve(self) -> Callable[..., Any]:
        if self._add_message is not None:
            return self._add_message
        from radbot.web.db.chat_operations import add_message  # lazy

        return add_message

    async def publish(self, event: ResultEvent) -> None:
        if isinstance(event, ScheduledTaskEvent):
            if not event.session_id or not event.response:
                return
            add = self._resolve()
            await asyncio.to_thread(
                add,
                event.session_id,
                "assistant",
                event.response,
                user_id="web_user",
            )
            return
        if isinstance(event, ReminderEvent):
            if not event.deliver_to_chat or not event.session_id:
                return
            add = self._resolve()
            await asyncio.to_thread(
                add,
                event.session_id,
                "system",
                f"[Reminder] {event.message}",
                user_id="web_user",
            )
            return
        if isinstance(event, (AlertEvent, HeartbeatEvent)):
            logger.debug(
                "ChatHistorySink: skipping %s (not chat-bound)",
                type(event).__name__,
            )
            return


class NtfySink:
    """Push a notification via ntfy. No-op if the ntfy client is unconfigured."""

    name = "ntfy"

    def __init__(self, client_getter: Callable[[], Any]) -> None:
        self._getter = client_getter

    async def publish(self, event: ResultEvent) -> None:
        client = self._getter()
        if not client:
            logger.debug("NtfySink: client unavailable, skipping push")
            return
        tags = getattr(event, "tags", "") or ""
        session_id = getattr(event, "session_id", None) or None
        await client.publish(
            title=event.title,
            message=event.message,
            priority=event.priority,
            tags=tags,
            session_id=session_id,
            skip_notification=True,
        )


class NotificationsTableSink:
    """Insert a notifications row and broadcast its badge over WS.

    Pairing the row write with the badge broadcast keeps a single source of
    truth for the badge's `notification_id` (it comes from the DB insert).
    """

    name = "notifications"

    def __init__(
        self,
        ws_broadcaster: Optional[WsBroadcaster] = None,
        create_notification: Optional[Callable[..., dict]] = None,
    ) -> None:
        self._broadcast = ws_broadcaster
        self._create = create_notification

    def _resolve(self) -> Callable[..., dict]:
        if self._create is not None:
            return self._create
        from radbot.tools.notifications.db import create_notification  # lazy

        return create_notification

    @staticmethod
    def _classify(event: ResultEvent) -> tuple[Optional[str], Optional[str], dict]:
        if isinstance(event, ScheduledTaskEvent):
            return (
                "scheduled_task",
                event.task_id or None,
                {"task_name": event.task_name, "prompt": event.prompt[:500]},
            )
        if isinstance(event, ReminderEvent):
            return (
                "reminder",
                event.reminder_id or None,
                {"reminder_id": event.reminder_id},
            )
        if isinstance(event, AlertEvent):
            # Only the initial "received" phase produces a notifications row;
            # later phases (investigating/resolved/failed) update the alert_events
            # row instead and would otherwise spam the notifications table.
            if event.phase != "received":
                logger.debug(
                    "NotificationsTableSink: skipping AlertEvent phase=%s",
                    event.phase,
                )
                return (None, None, {})
            return (
                "alert",
                event.alert_id or None,
                {
                    "alertname": event.alertname,
                    "severity": event.severity,
                    "status": "firing",
                    "instance": event.instance,
                },
            )
        if isinstance(event, HeartbeatEvent):
            return ("heartbeat", None, {"channel": "ntfy"})
        return (None, None, {})

    async def publish(self, event: ResultEvent) -> None:
        notif_type, source_id, metadata = self._classify(event)
        if notif_type is None:
            return

        message = event.message[:4000] if event.message else "(no message)"
        create = self._resolve()
        notif = await asyncio.to_thread(
            create,
            type=notif_type,
            title=event.title,
            message=message,
            source_id=source_id,
            session_id=getattr(event, "session_id", None) or None,
            priority=event.priority,
            metadata=metadata,
        )
        if self._broadcast and notif and notif.get("notification_id"):
            payload = WsNotificationPayload(
                content=_WsNotificationContent(
                    notification_id=str(notif["notification_id"]),
                    notification_type=notif_type,
                    title=event.title,
                ),
            ).model_dump()
            await self._broadcast(payload)


class WebSocketChatSink:
    """Broadcast a system-message WS payload for events that should surface in chat.

    Today only delivered reminders use this — scheduled tasks expose their
    response via the chat history sink directly.
    """

    name = "ws_chat"

    def __init__(self, ws_broadcaster: WsBroadcaster) -> None:
        self._broadcast = ws_broadcaster

    async def publish(self, event: ResultEvent) -> None:
        if isinstance(event, ReminderEvent) and event.deliver_to_chat:
            payload = WsSystemMessagePayload(
                content=f"[Reminder] {event.message}",
            ).model_dump()
            await self._broadcast(payload)
            return
        logger.debug(
            "WebSocketChatSink: skipping %s (not a delivered reminder)",
            type(event).__name__,
        )


class AlertResultBroadcastSink:
    """Broadcast the legacy `alert_result` WS payload for terminal AlertEvents.

    The alertmanager pipeline historically emitted a final WS broadcast after
    each remediation run with the prompt+response. The Notifier seam folds
    that into a single AlertEvent publish on phase `resolved`/`failed`; this
    sink is responsible for the WS broadcast piece, while NtfySink handles
    the user-facing push.
    """

    name = "alert_result_ws"

    def __init__(self, ws_broadcaster: WsBroadcaster) -> None:
        self._broadcast = ws_broadcaster

    async def publish(self, event: ResultEvent) -> None:
        if not isinstance(event, AlertEvent):
            logger.debug(
                "AlertResultBroadcastSink: skipping %s (not an AlertEvent)",
                type(event).__name__,
            )
            return
        if event.phase not in ("resolved", "failed"):
            logger.debug(
                "AlertResultBroadcastSink: skipping AlertEvent phase=%s",
                event.phase,
            )
            return
        if not event.response:
            logger.debug(
                "AlertResultBroadcastSink: skipping AlertEvent phase=%s "
                "(no response payload)",
                event.phase,
            )
            return
        from datetime import datetime  # lazy

        await self._broadcast(
            {
                "type": "alert_result",
                "alert_id": event.alert_id,
                "alertname": event.alertname,
                "severity": event.severity,
                "prompt": event.prompt[:500],
                "response": event.response[:1000],
                "timestamp": datetime.now().isoformat(),
            }
        )


# ---------------------------------------------------------------------------
# Notifier — owns the fan-out
# ---------------------------------------------------------------------------


class Notifier:
    """Fan a `ResultEvent` to all configured sinks concurrently.

    Per-sink errors are caught + logged; `publish()` always returns `None`.
    Each sink call is wrapped in `asyncio.wait_for(timeout=...)` to prevent
    one slow sink from blocking the rest.
    """

    def __init__(
        self,
        sinks: list[NotificationSink],
        sink_timeout: float = DEFAULT_SINK_TIMEOUT,
    ) -> None:
        self._sinks: list[NotificationSink] = list(sinks)
        self._timeout = sink_timeout

    @property
    def sinks(self) -> list[NotificationSink]:
        return list(self._sinks)

    async def publish(self, event: ResultEvent) -> None:
        if not self._sinks:
            logger.debug(
                "Notifier has no sinks configured; dropping %s",
                type(event).__name__,
            )
            return

        skip = getattr(event, "skip_sinks", frozenset())
        active = [s for s in self._sinks if s.name not in skip]
        if not active:
            return

        async def _run(sink: NotificationSink) -> None:
            try:
                await asyncio.wait_for(sink.publish(event), timeout=self._timeout)
            except asyncio.TimeoutError:
                logger.error(
                    "Notifier sink '%s' timed out (>%.1fs) on %s — event dropped",
                    sink.name,
                    self._timeout,
                    type(event).__name__,
                )
            except Exception:
                logger.error(
                    "Notifier sink '%s' raised on %s — event dropped",
                    sink.name,
                    type(event).__name__,
                    exc_info=True,
                )

        await asyncio.gather(*[_run(s) for s in active], return_exceptions=True)


# ---------------------------------------------------------------------------
# Module-level singleton accessor
# ---------------------------------------------------------------------------


_notifier: Optional[Notifier] = None


def set_notifier(notifier: Optional[Notifier]) -> None:
    """Install the process-wide Notifier (called once at web startup)."""
    global _notifier
    _notifier = notifier


def get_notifier() -> Optional[Notifier]:
    """Return the process-wide Notifier, or None if not yet constructed."""
    return _notifier


def reset_notifier() -> None:
    """Clear the process-wide Notifier (test helper)."""
    global _notifier
    _notifier = None


def build_default_notifier(ws_broadcaster: WsBroadcaster) -> Notifier:
    """Construct the production Notifier with the canonical sinks."""
    from radbot.tools.ntfy.ntfy_client import get_ntfy_client  # lazy

    return Notifier(
        sinks=[
            ChatHistorySink(),
            NtfySink(client_getter=get_ntfy_client),
            NotificationsTableSink(ws_broadcaster=ws_broadcaster),
            WebSocketChatSink(ws_broadcaster=ws_broadcaster),
            AlertResultBroadcastSink(ws_broadcaster=ws_broadcaster),
        ]
    )
