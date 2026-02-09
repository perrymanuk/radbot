"""
FastAPI router for webhook trigger and management endpoints.
"""

import hashlib
import hmac
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


class WebhookCreateBody(BaseModel):
    name: str
    path_suffix: str
    prompt_template: str
    secret: Optional[str] = None


# ---- management endpoints ----

@router.get("/definitions")
async def list_webhook_definitions():
    """List all webhook definitions."""
    try:
        from radbot.tools.webhooks.db import list_webhooks
        from radbot.tools.shared.serialization import serialize_rows
        webhooks = list_webhooks()
        return serialize_rows(webhooks, mask_fields={"secret": "***"})
    except Exception as e:
        logger.error(f"Error listing webhooks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/definitions")
async def create_webhook_definition(body: WebhookCreateBody):
    """Create a webhook definition via REST."""
    try:
        from radbot.tools.webhooks.db import create_webhook
        row = create_webhook(
            name=body.name,
            path_suffix=body.path_suffix,
            prompt_template=body.prompt_template,
            secret=body.secret,
        )
        return {"status": "success", "webhook_id": str(row["webhook_id"])}
    except Exception as e:
        logger.error(f"Error creating webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/definitions/{webhook_id}")
async def delete_webhook_definition(webhook_id: str):
    """Delete a webhook definition."""
    try:
        wh_uuid = uuid.UUID(webhook_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    try:
        from radbot.tools.webhooks.db import delete_webhook
        success = delete_webhook(wh_uuid)
        if success:
            return {"status": "success", "webhook_id": webhook_id}
        raise HTTPException(status_code=404, detail="Webhook not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ---- trigger endpoint ----

def _verify_hmac(secret: str, body: bytes, signature: str) -> bool:
    """Verify HMAC-SHA256 signature."""
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/trigger/{path_suffix}")
async def trigger_webhook(path_suffix: str, request: Request):
    """
    Trigger a webhook. External services POST JSON here.

    The payload is rendered into the webhook's prompt template,
    sent to the agent, and the response is pushed to all active WebSocket connections.
    """
    try:
        from radbot.tools.webhooks.db import get_webhook_by_path, record_trigger
        from radbot.tools.webhooks.template_renderer import render_template
    except Exception as e:
        logger.error(f"Failed to import webhook modules: {e}")
        raise HTTPException(status_code=500, detail="Webhook system not available")

    # Look up webhook
    webhook = get_webhook_by_path(path_suffix)
    if not webhook:
        raise HTTPException(status_code=404, detail=f"No webhook found for path: {path_suffix}")

    # Read raw body for HMAC verification
    raw_body = await request.body()

    # Verify HMAC if secret is set
    if webhook.get("secret"):
        sig_header = request.headers.get("X-Signature-256", "") or request.headers.get("X-Hub-Signature-256", "")
        # Strip "sha256=" prefix if present (GitHub style)
        sig = sig_header.replace("sha256=", "")
        if not sig or not _verify_hmac(webhook["secret"], raw_body, sig):
            raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse JSON payload
    try:
        payload: Dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Render the prompt
    rendered_prompt = render_template(webhook["prompt_template"], payload)
    logger.info(f"Webhook '{webhook['name']}' triggered, rendered prompt: {rendered_prompt[:100]}")

    # Record the trigger
    try:
        record_trigger(webhook["webhook_id"])
    except Exception as e:
        logger.warning(f"Failed to record webhook trigger: {e}")

    # Process the prompt asynchronously and push results via WebSocket
    import asyncio
    asyncio.create_task(
        _process_and_broadcast(
            webhook_id=str(webhook["webhook_id"]),
            webhook_name=webhook["name"],
            prompt=rendered_prompt,
        )
    )

    return {"status": "accepted", "webhook_id": str(webhook["webhook_id"])}


async def _process_and_broadcast(webhook_id: str, webhook_name: str, prompt: str) -> None:
    """Send the rendered prompt to the agent and broadcast the result."""
    response_text = ""
    try:
        from radbot.web.api.session.dependencies import get_or_create_runner_for_session
        from radbot.web.api.session import get_session_manager

        session_manager = get_session_manager()
        runner = await get_or_create_runner_for_session(
            f"webhook_{webhook_id}", session_manager
        )
        result = await runner.process_message(prompt)
        response_text = result.get("response", "")
        logger.info(f"Webhook '{webhook_name}' processed, response length={len(response_text)}")
    except Exception as e:
        response_text = f"Error processing webhook: {e}"
        logger.error(f"Error processing webhook '{webhook_name}': {e}", exc_info=True)

    # Broadcast to all active WebSocket connections
    try:
        from radbot.web.app import manager
        message_payload = {
            "type": "webhook_result",
            "webhook_id": webhook_id,
            "webhook_name": webhook_name,
            "prompt": prompt,
            "response": response_text,
            "timestamp": datetime.now().isoformat(),
        }
        await manager.broadcast_to_all_sessions(message_payload)
    except Exception as e:
        logger.error(f"Failed to broadcast webhook result: {e}")
