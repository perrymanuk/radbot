"""Nomad infrastructure integration e2e tests.

Read-only tests via agent chat. Auto-skipped if Nomad is unreachable.
"""

import uuid

import pytest

from tests.e2e.helpers.assertions import (
    assert_response_contains_any,
    assert_response_not_empty,
)
from tests.e2e.helpers.ws_client import WSTestClient

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.slow,
    pytest.mark.requires_nomad,
    pytest.mark.timeout(120),
]


class TestNomadIntegration:
    async def test_list_nomad_jobs(self, live_server):
        """Ask to list Nomad jobs."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response("List all Nomad jobs")
            assert_response_not_empty(result)
            assert_response_contains_any(
                result, "job", "nomad", "running", "status", "no job"
            )
        finally:
            await ws.close()

    async def test_get_nomad_job_status(self, live_server):
        """Ask about a specific Nomad job status."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "Show me the status of the radbot Nomad job"
            )
            assert_response_not_empty(result)
            assert_response_contains_any(
                result,
                "radbot",
                "status",
                "running",
                "allocation",
                "healthy",
                "not found",
                "job",
            )
        finally:
            await ws.close()

    async def test_nomad_allocation_logs(self, live_server):
        """Ask for Nomad job logs."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "Show me the recent logs for the radbot Nomad job"
            )
            assert_response_not_empty(result)
            assert_response_contains_any(
                result,
                "log",
                "radbot",
                "output",
                "stderr",
                "stdout",
                "not found",
                "error",
            )
        finally:
            await ws.close()

    async def test_nomad_service_health(self, live_server):
        """Check Nomad service health."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "Check the health of Nomad services"
            )
            assert_response_not_empty(result)
            assert_response_contains_any(
                result, "health", "service", "nomad", "healthy", "status"
            )
        finally:
            await ws.close()
