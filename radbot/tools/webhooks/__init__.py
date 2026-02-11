"""
Webhook tools for the radbot agent.

This package provides tools for creating, listing, and deleting webhooks
that allow external services to trigger agent actions via HTTP POST.
"""

from .db import init_webhook_schema
from .webhook_tools import (
    WEBHOOK_TOOLS,
    create_webhook_tool,
    delete_webhook_tool,
    list_webhooks_tool,
)

__all__ = [
    "create_webhook_tool",
    "list_webhooks_tool",
    "delete_webhook_tool",
    "WEBHOOK_TOOLS",
    "init_webhook_schema",
]
