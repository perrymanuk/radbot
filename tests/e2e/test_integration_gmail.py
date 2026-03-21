"""Gmail integration e2e tests.

Read-only tests via agent chat. Auto-skipped if Gmail credentials unavailable.
"""

import uuid

import pytest

from tests.e2e.helpers.assertions import assert_response_contains_any, assert_response_not_empty
from tests.e2e.helpers.ws_client import WSTestClient

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.slow,
    pytest.mark.requires_gmail,
    pytest.mark.timeout(120),
]


class TestGmailIntegration:
    async def test_list_emails(self, live_server):
        """Ask about recent emails."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response("Show my recent emails")
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result, "email", "inbox", "message", "mail", "no email", "subject"
            )
        finally:
            await ws.close()

    async def test_search_emails(self, live_server):
        """Search emails with a query."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "Search my emails for messages from github"
            )
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result, "email", "github", "message", "found", "no result",
                "subject", "from", "mail",
            )
        finally:
            await ws.close()

    async def test_list_gmail_accounts(self, live_server):
        """Ask about configured Gmail accounts."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "What Gmail accounts are configured?"
            )
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result, "account", "gmail", "email", "configured", "@"
            )
        finally:
            await ws.close()
