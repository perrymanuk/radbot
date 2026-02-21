"""Reminders API e2e tests."""

from datetime import datetime, timedelta, timezone

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio(loop_scope="session")]


class TestRemindersAPI:
    def _future_iso(self, hours: int = 8760) -> str:
        """Return an ISO datetime string in the future (default: 1 year)."""
        dt = datetime.now(timezone.utc) + timedelta(hours=hours)
        return dt.isoformat()

    async def test_create_reminder(self, client, cleanup, test_prefix):
        """POST /api/reminders should create a reminder."""
        resp = await client.post(
            "/api/reminders",
            json={
                "message": f"{test_prefix}_reminder",
                "remind_at": self._future_iso(),
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "reminder_id" in data
        cleanup.track("reminder", data["reminder_id"])

    async def test_list_reminders(self, client, cleanup, test_prefix):
        """GET /api/reminders should include the created reminder."""
        # Create
        create_resp = await client.post(
            "/api/reminders",
            json={
                "message": f"{test_prefix}_rem_list",
                "remind_at": self._future_iso(),
            },
        )
        reminder_id = create_resp.json()["reminder_id"]
        cleanup.track("reminder", reminder_id)

        # List
        resp = await client.get("/api/reminders")
        assert resp.status_code == 200
        reminders = resp.json()
        assert isinstance(reminders, list)
        ids = [str(r.get("reminder_id")) for r in reminders]
        assert reminder_id in ids

    async def test_delete_reminder(self, client, test_prefix):
        """DELETE /api/reminders/{id} should remove the reminder."""
        # Create
        create_resp = await client.post(
            "/api/reminders",
            json={
                "message": f"{test_prefix}_rem_del",
                "remind_at": self._future_iso(),
            },
        )
        reminder_id = create_resp.json()["reminder_id"]

        # Delete
        resp = await client.delete(f"/api/reminders/{reminder_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    async def test_create_past_reminder(self, client):
        """POST /api/reminders with a past time should return 400."""
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        resp = await client.post(
            "/api/reminders",
            json={
                "message": "past reminder",
                "remind_at": past,
            },
        )
        assert resp.status_code == 400
