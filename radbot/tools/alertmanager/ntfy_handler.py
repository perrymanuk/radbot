"""Handler for alertmanager messages received via ntfy subscription.

Registered as a handler on the ntfy subscriber to parse incoming messages
and route them through the alert processor.
"""

import json
import logging
import uuid
from typing import Any, Dict

logger = logging.getLogger(__name__)


async def handle_alertmanager_message(message: Dict[str, Any]) -> None:
    """Parse an ntfy message as an alertmanager payload and process each alert.

    Handles two formats:
    1. Standard alertmanager webhook JSON in the message body (alerts[] array)
    2. Plain text ntfy messages (treated as a single firing alert)

    Args:
        message: The ntfy message dict with keys: id, time, topic, title, message, tags, priority
    """
    from radbot.tools.alertmanager.processor import process_alert_from_payload

    raw_message = message.get("message", "")
    ntfy_title = message.get("title", "")
    ntfy_id = message.get("id", "")

    logger.info(
        f"Alertmanager ntfy handler: processing message "
        f"(title='{ntfy_title}', id={ntfy_id})"
    )

    # Try to parse as JSON (alertmanager webhook format)
    try:
        body = json.loads(raw_message)
    except (json.JSONDecodeError, TypeError):
        body = None

    if body and isinstance(body, dict) and "alerts" in body:
        # Standard alertmanager webhook format
        alerts = body.get("alerts", [])
        logger.info(
            f"Alertmanager ntfy handler: received {len(alerts)} alerts "
            f"(status={body.get('status')}, receiver={body.get('receiver')})"
        )
        for alert in alerts:
            # Ensure fingerprint exists
            if not alert.get("fingerprint"):
                alert["fingerprint"] = str(uuid.uuid4())
            try:
                await process_alert_from_payload(alert)
            except Exception as e:
                logger.error(
                    f"Failed to process alert {alert.get('labels', {}).get('alertname', '?')}: {e}",
                    exc_info=True,
                )
    else:
        # Non-standard format — treat the ntfy message as a single alert
        logger.info("Alertmanager ntfy handler: non-standard format, creating synthetic alert")
        synthetic_alert = {
            "status": "firing",
            "labels": {
                "alertname": ntfy_title or "ntfy_alert",
                "severity": _ntfy_priority_to_severity(message.get("priority", 3)),
            },
            "annotations": {
                "summary": raw_message or ntfy_title or "Alert received via ntfy",
            },
            "fingerprint": ntfy_id or str(uuid.uuid4()),
        }
        try:
            await process_alert_from_payload(synthetic_alert)
        except Exception as e:
            logger.error(f"Failed to process synthetic alert: {e}", exc_info=True)


def _ntfy_priority_to_severity(priority: int) -> str:
    """Map ntfy priority (1-5) to alertmanager severity."""
    if priority >= 5:
        return "critical"
    if priority >= 4:
        return "error"
    if priority >= 3:
        return "warning"
    return "info"
