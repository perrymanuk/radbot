"""Gmail function tools for ADK integration with multi-account support."""

import logging
from typing import Any, Dict, List, Optional

from google.adk.tools import FunctionTool
from pydantic import BaseModel, Field

from radbot.tools.gmail.gmail_auth import discover_accounts
from radbot.tools.gmail.gmail_manager import GmailManager, get_gmail_manager

logger = logging.getLogger(__name__)


# --- Pydantic parameter models ---


class ListEmailsParameters(BaseModel):
    """Parameters for list_emails function."""

    max_results: int = Field(
        default=10,
        description="Maximum number of emails to return",
        ge=1,
        le=50,
    )
    label: str = Field(
        default="INBOX",
        description="Gmail label to list from (e.g. INBOX, SENT, STARRED, IMPORTANT, UNREAD)",
    )
    account: Optional[str] = Field(
        default=None,
        description=(
            "Gmail account label to use (e.g. 'personal', 'work'). "
            "Use list_gmail_accounts to see available accounts. "
            "If not specified, uses the default account."
        ),
    )


class SearchEmailsParameters(BaseModel):
    """Parameters for search_emails function."""

    query: str = Field(
        description=(
            "Gmail search query. Supports Gmail operators like "
            "from:, to:, subject:, newer_than:, older_than:, has:attachment, "
            "is:unread, label:, filename:, and free text."
        ),
    )
    max_results: int = Field(
        default=10,
        description="Maximum number of results to return",
        ge=1,
        le=50,
    )
    account: Optional[str] = Field(
        default=None,
        description=(
            "Gmail account label to use (e.g. 'personal', 'work'). "
            "Use list_gmail_accounts to see available accounts. "
            "If not specified, uses the default account."
        ),
    )


class GetEmailParameters(BaseModel):
    """Parameters for get_email function."""

    message_id: str = Field(
        description="The Gmail message ID to retrieve",
    )
    account: Optional[str] = Field(
        default=None,
        description=(
            "Gmail account label to use (e.g. 'personal', 'work'). "
            "Use list_gmail_accounts to see available accounts. "
            "If not specified, uses the default account."
        ),
    )


# --- Core functions (accept manager parameter for testability) ---


def list_emails(
    manager: Optional[GmailManager] = None,
    max_results: int = 10,
    label: str = "INBOX",
    account: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List recent emails from Gmail."""
    if manager is None:
        manager = get_gmail_manager(account=account)
    return manager.list_inbox(max_results=max_results, label=label)


def search_emails(
    manager: Optional[GmailManager] = None,
    query: str = "",
    max_results: int = 10,
    account: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Search emails using Gmail query syntax."""
    if manager is None:
        manager = get_gmail_manager(account=account)
    return manager.search(query=query, max_results=max_results)


def get_email(
    manager: Optional[GmailManager] = None,
    message_id: str = "",
    account: Optional[str] = None,
) -> Dict[str, Any]:
    """Get full email content by message ID."""
    if manager is None:
        manager = get_gmail_manager(account=account)
    return manager.get_message(message_id=message_id)


# --- Wrapper functions for ADK (no manager parameter) ---


def list_emails_wrapper(
    max_results: int = 10,
    label: str = "INBOX",
    account: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List recent emails from your Gmail inbox or another label.

    Supports multiple Gmail accounts. Use list_gmail_accounts to see which
    accounts are available, then pass the account label to read from a
    specific account (e.g. account="work").

    Args:
        max_results: Maximum number of emails to return (1-50).
        label: Gmail label to list from (e.g. INBOX, SENT, STARRED, IMPORTANT).
        account: Gmail account label (e.g. "personal", "work"). Omit for default.

    Returns:
        List of email summaries with id, subject, from, date, and snippet.
    """
    try:
        result = list_emails(max_results=max_results, label=label, account=account)
        if (
            isinstance(result, list)
            and result
            and isinstance(result[0], dict)
            and "error" in result[0]
        ):
            logger.error(f"Gmail list error: {result[0]['error']}")
            return []
        return result
    except Exception as e:
        logger.error(f"Exception listing emails: {e}")
        return []


def search_emails_wrapper(
    query: str,
    max_results: int = 10,
    account: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Search emails using Gmail search syntax.

    Supports multiple Gmail accounts. Use list_gmail_accounts to see which
    accounts are available, then pass the account label to search a
    specific account (e.g. account="work").

    Supports Gmail search operators:
    - from:user@example.com
    - subject:meeting
    - newer_than:7d
    - older_than:1m
    - has:attachment
    - is:unread
    - label:important
    - filename:pdf
    - Combined: from:boss@work.com newer_than:3d subject:report

    Args:
        query: Gmail search query string.
        max_results: Maximum number of results to return (1-50).
        account: Gmail account label (e.g. "personal", "work"). Omit for default.

    Returns:
        List of matching email summaries with id, subject, from, date, and snippet.
    """
    try:
        if not query:
            return [{"error": "Query is required for email search"}]
        result = search_emails(query=query, max_results=max_results, account=account)
        if (
            isinstance(result, list)
            and result
            and isinstance(result[0], dict)
            and "error" in result[0]
        ):
            logger.error(f"Gmail search error: {result[0]['error']}")
            return []
        return result
    except Exception as e:
        logger.error(f"Exception searching emails: {e}")
        return []


def get_email_wrapper(
    message_id: str,
    account: Optional[str] = None,
) -> Dict[str, Any]:
    """Get the full content of an email by its message ID.

    Returns the complete email including headers (from, to, subject, date),
    the decoded body text, and a list of any attachments.

    Args:
        message_id: The Gmail message ID (obtained from list_emails or search_emails).
        account: Gmail account label (e.g. "personal", "work"). Omit for default.

    Returns:
        Full email content with subject, from, to, date, body text, and attachments.
    """
    try:
        if not message_id:
            return {"error": "message_id is required"}
        result = get_email(message_id=message_id, account=account)
        if isinstance(result, dict) and "error" in result:
            logger.error(f"Gmail get error: {result['error']}")
            return {"status": "error", "message": result["error"]}
        return result
    except Exception as e:
        logger.error(f"Exception getting email: {e}")
        return {"status": "error", "message": str(e)}


def list_gmail_accounts_wrapper() -> List[Dict[str, str]]:
    """List all configured Gmail accounts.

    Returns the account labels and email addresses for all Gmail accounts
    that have been set up. Use the account label with other Gmail tools
    to specify which account to use.

    To add a new account, run:
        python -m radbot.tools.gmail.setup --account <label>

    Returns:
        List of configured accounts with 'account' (label) and 'email' fields.
    """
    try:
        accounts = discover_accounts()
        if not accounts:
            return [
                {
                    "message": "No Gmail accounts configured. Run: python -m radbot.tools.gmail.setup --account <label>"
                }
            ]
        # Don't return token_file path to the agent
        return [{"account": a["account"], "email": a["email"]} for a in accounts]
    except Exception as e:
        logger.error(f"Exception listing Gmail accounts: {e}")
        return [{"error": str(e)}]


# --- FunctionTool definitions ---

list_emails_tool = FunctionTool(list_emails_wrapper)
search_emails_tool = FunctionTool(search_emails_wrapper)
get_email_tool = FunctionTool(get_email_wrapper)
list_gmail_accounts_tool = FunctionTool(list_gmail_accounts_wrapper)
