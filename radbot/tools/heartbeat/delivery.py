"""Heartbeat delivery — pluggable transport for the digest.

Default channel is ntfy (per EX3 open-question resolution). Transport
is intentionally a thin adapter so email / other channels can be added
behind the same `deliver_digest()` signature later.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def deliver_digest(
    markdown: str,
    *,
    title: str = "Heartbeat",
    tags: str = "sunrise,robot",
) -> bool:
    """Deliver a digest via the configured proactive channel.

    Returns True if delivered, False otherwise (including the "nothing
    worth bothering you with" empty-digest case).
    """
    if not markdown:
        logger.info("Heartbeat: digest empty, nothing to deliver")
        return False

    try:
        from radbot.tools.ntfy.ntfy_client import get_ntfy_client

        client = get_ntfy_client()
    except Exception as e:
        logger.warning("Heartbeat: ntfy client unavailable: %s", e)
        client = None

    if client is None:
        logger.info("Heartbeat: no delivery channel configured, skipping")
        return False

    # ntfy truncates at 2000 chars inside publish(), but signal a soft cap too.
    body = markdown[:2000]
    try:
        result = await client.publish(title=title, message=body, tags=tags)
    except Exception as e:
        logger.warning("Heartbeat: ntfy publish raised: %s", e)
        return False

    if result is None:
        return False

    # Record in the unified notifications table so it surfaces in the UI.
    try:
        from radbot.tools.notifications.db import create_notification

        create_notification(
            type="heartbeat",
            title=title,
            message=markdown[:4000],
            metadata={"channel": "ntfy"},
        )
    except Exception as e:
        logger.debug("Heartbeat: notifications write failed (non-fatal): %s", e)

    return True
