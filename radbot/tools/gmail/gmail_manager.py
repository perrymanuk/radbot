"""Gmail Manager class for Gmail integration with multi-account support."""

import logging
from typing import Any, Dict, List, Optional

from radbot.tools.gmail.gmail_auth import discover_accounts, get_gmail_service
from radbot.tools.gmail.gmail_operations import (
    get_message,
    list_messages,
    search_messages,
)

logger = logging.getLogger(__name__)


class GmailManager:
    """Manages Gmail operations for a specific account."""

    def __init__(self, account: Optional[str] = None):
        self.account = account
        self.service = None

    def authenticate(self) -> bool:
        """Authenticate with Gmail API.

        Returns:
            True if authentication was successful, False otherwise.
        """
        try:
            self.service = get_gmail_service(account=self.account)
            profile = self.service.users().getProfile(userId="me").execute()
            email = profile.get("emailAddress", "unknown")
            label = self.account or "default"
            logger.info(f"Gmail '{label}' authenticated as: {email}")
            return True
        except Exception as e:
            logger.error(f"Gmail authentication failed for '{self.account or 'default'}': {e}")
            self.service = None
            return False

    def list_inbox(
        self,
        max_results: int = 10,
        label: str = "INBOX",
        query: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List messages from a label (default INBOX)."""
        if not self.service:
            return [{"error": "Gmail not authenticated"}]

        label_ids = [label] if label else None
        return list_messages(
            self.service,
            max_results=max_results,
            label_ids=label_ids,
            query=query,
        )

    def search(
        self,
        query: str,
        max_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search messages using Gmail query syntax."""
        if not self.service:
            return [{"error": "Gmail not authenticated"}]

        return search_messages(self.service, query=query, max_results=max_results)

    def get_message(self, message_id: str) -> Dict[str, Any]:
        """Get a full message by ID."""
        if not self.service:
            return {"error": "Gmail not authenticated"}

        result = get_message(self.service, message_id)
        if result is None:
            return {"error": f"Failed to retrieve message {message_id}"}
        return result


# Cache managers by account label
_gmail_managers: Dict[str, GmailManager] = {}


def get_gmail_manager(account: Optional[str] = None) -> GmailManager:
    """Get a GmailManager for the given account, authenticating on first call.

    Args:
        account: Account label (e.g. "personal", "work"). None for default.

    Returns:
        GmailManager instance.
    """
    key = account or "default"
    if key not in _gmail_managers:
        manager = GmailManager(account=account)
        auth_ok = manager.authenticate()
        if not auth_ok:
            logger.warning(f"Gmail authentication failed for '{key}'. Operations will not work.")
        _gmail_managers[key] = manager
    return _gmail_managers[key]


def get_all_account_labels() -> List[str]:
    """Get labels for all configured Gmail accounts.

    Returns:
        List of account labels (e.g. ["personal", "work"]).
    """
    accounts = discover_accounts()
    return [a["account"] for a in accounts]
