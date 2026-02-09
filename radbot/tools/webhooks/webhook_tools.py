"""
Agent tools for webhook management.

Provides create, list, and delete tools that the agent can invoke to manage
webhook definitions.
"""

import logging
import traceback
from typing import Dict, Any, Optional

from google.adk.tools import FunctionTool

from radbot.tools.shared.errors import truncate_error
from radbot.tools.shared.serialization import serialize_rows
from radbot.tools.shared.validation import validate_uuid
from . import db as webhook_db

logger = logging.getLogger(__name__)


def create_webhook(
    name: str,
    path_suffix: str,
    prompt_template: str,
    secret: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Registers a new webhook endpoint.

    External services can POST JSON to /api/webhooks/trigger/<path_suffix>.
    The payload is rendered into the prompt_template and sent to the agent.

    Args:
        name: A unique human-readable name (e.g. "GitHub Push").
        path_suffix: The URL path suffix (e.g. "github-push" →
            /api/webhooks/trigger/github-push). Must be unique.
        prompt_template: A template string with {{payload.key.subkey}} placeholders
            that will be filled from the incoming JSON payload.
            Example: "New commit on {{payload.repository.name}} by {{payload.pusher.name}}"
        secret: Optional HMAC secret for validating incoming requests.

    Returns:
        On success: {"status": "success", "webhook_id": "...", "trigger_url": "/api/webhooks/trigger/<path_suffix>"}
        On failure: {"status": "error", "message": "..."}
    """
    try:
        row = webhook_db.create_webhook(
            name=name,
            path_suffix=path_suffix,
            prompt_template=prompt_template,
            secret=secret,
        )
        webhook_id = str(row["webhook_id"])
        return {
            "status": "success",
            "webhook_id": webhook_id,
            "trigger_url": f"/api/webhooks/trigger/{path_suffix}",
        }
    except Exception as e:
        error_message = f"Failed to create webhook: {str(e)}"
        logger.error(f"Error in create_webhook: {error_message}")
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": truncate_error(error_message)}


def list_webhooks() -> Dict[str, Any]:
    """
    Lists all registered webhooks.

    Returns:
        On success: {"status": "success", "webhooks": [...]}
        On failure: {"status": "error", "message": "..."}
    """
    try:
        webhooks = webhook_db.list_webhooks()
        serialised = serialize_rows(webhooks, mask_fields={"secret": "***"})
        for item, w in zip(serialised, webhooks):
            item["trigger_url"] = f"/api/webhooks/trigger/{w['path_suffix']}"

        return {"status": "success", "webhooks": serialised}
    except Exception as e:
        error_message = f"Failed to list webhooks: {str(e)}"
        logger.error(f"Error in list_webhooks: {error_message}")
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": truncate_error(error_message)}


def delete_webhook(webhook_id: str) -> Dict[str, Any]:
    """
    Deletes a webhook by its UUID.

    Args:
        webhook_id: The UUID of the webhook to delete.

    Returns:
        On success: {"status": "success", "webhook_id": "..."}
        On failure: {"status": "error", "message": "..."}
    """
    try:
        wh_uuid, err = validate_uuid(webhook_id, "webhook ID")
        if err:
            return err

        success = webhook_db.delete_webhook(wh_uuid)
        if success:
            return {"status": "success", "webhook_id": webhook_id}
        else:
            return {"status": "error", "message": f"Webhook {webhook_id} not found."}
    except Exception as e:
        error_message = f"Failed to delete webhook: {str(e)}"
        logger.error(f"Error in delete_webhook: {error_message}")
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": truncate_error(error_message)}


# Wrap as ADK FunctionTools
create_webhook_tool = FunctionTool(create_webhook)
list_webhooks_tool = FunctionTool(list_webhooks)
delete_webhook_tool = FunctionTool(delete_webhook)

WEBHOOK_TOOLS = [
    create_webhook_tool,
    list_webhooks_tool,
    delete_webhook_tool,
]
