"""
Push notification support via ntfy.sh.

This package provides an async HTTP client for publishing push notifications
to ntfy topics. Notifications are sent for scheduled task results and
reminders so the user receives them even when no browser tab is open.
"""

from .ntfy_client import NtfyClient, get_ntfy_client, reset_ntfy_client

__all__ = [
    "NtfyClient",
    "get_ntfy_client",
    "reset_ntfy_client",
]
