"""Gmail read-only integration for radbot with multi-account support."""

from radbot.tools.gmail.gmail_auth import get_gmail_service
from radbot.tools.gmail.gmail_manager import GmailManager
from radbot.tools.gmail.gmail_tools import (
    get_email_tool,
    list_emails_tool,
    list_gmail_accounts_tool,
    search_emails_tool,
)

__all__ = [
    "get_gmail_service",
    "GmailManager",
    "list_emails_tool",
    "search_emails_tool",
    "get_email_tool",
    "list_gmail_accounts_tool",
]
