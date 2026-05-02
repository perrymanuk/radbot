"""Heartbeat delivery — fan out the digest through the Notifier seam.

Default channel is ntfy (per EX3 open-question resolution); the Notifier's
NtfySink owns the push and the NotificationsTableSink owns the notifications
row. EX41 PR2 retired the inline ntfy + notifications calls in favour of one
HeartbeatEvent publish.
"""

from __future__ import annotations

import logging

from radbot.services.notifier import HeartbeatEvent, get_notifier

logger = logging.getLogger(__name__)


async def deliver_digest(
    markdown: str,
    *,
    title: str = "Heartbeat",
    tags: str = "sunrise,robot",
) -> bool:
    """Deliver a digest via the configured proactive channel.

    Returns True if delivered, False otherwise (including the "nothing
    worth bothering you with" empty-digest case and the "Notifier not
    initialized" / "no ntfy client" cases).
    """
    if not markdown:
        logger.info("Heartbeat: digest empty, nothing to deliver")
        return False

    notifier = get_notifier()
    if notifier is None:
        logger.warning("Heartbeat: Notifier not initialized, skipping delivery")
        return False

    # ntfy publishes truncate at 2000; the persisted digest keeps a higher cap.
    body = markdown[:2000]
    await notifier.publish(
        HeartbeatEvent(
            title=title,
            message=body,
            tags=tags,
            digest_markdown=markdown,
        )
    )
    return True
