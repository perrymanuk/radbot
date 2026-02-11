"""Tests for radbot.tools.shared utilities."""

import uuid
from datetime import datetime, timezone

from radbot.tools.shared.errors import truncate_error
from radbot.tools.shared.serialization import serialize_row, serialize_rows
from radbot.tools.shared.validation import validate_uuid

# ── serialization ────────────────────────────────────────────────────────────


class TestSerializeRow:
    def test_uuid_converted_to_str(self):
        uid = uuid.uuid4()
        assert serialize_row({"id": uid}) == {"id": str(uid)}

    def test_datetime_converted_to_isoformat(self):
        dt = datetime(2025, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
        assert serialize_row({"ts": dt}) == {"ts": dt.isoformat()}

    def test_plain_values_unchanged(self):
        row = {"name": "hello", "count": 42, "flag": True}
        assert serialize_row(row) == row

    def test_mask_fields_truthy(self):
        row = {"secret": "mysecret", "name": "hook"}
        result = serialize_row(row, mask_fields={"secret": "***"})
        assert result == {"secret": "***", "name": "hook"}

    def test_mask_fields_falsy(self):
        row = {"secret": None, "name": "hook"}
        result = serialize_row(row, mask_fields={"secret": "***"})
        assert result == {"secret": None, "name": "hook"}

    def test_mixed_types(self):
        uid = uuid.uuid4()
        dt = datetime(2025, 6, 1, tzinfo=timezone.utc)
        row = {"id": uid, "ts": dt, "name": "test", "count": 5}
        result = serialize_row(row)
        assert result == {
            "id": str(uid),
            "ts": dt.isoformat(),
            "name": "test",
            "count": 5,
        }


class TestSerializeRows:
    def test_empty_list(self):
        assert serialize_rows([]) == []

    def test_multiple_rows(self):
        uid1, uid2 = uuid.uuid4(), uuid.uuid4()
        rows = [{"id": uid1}, {"id": uid2}]
        result = serialize_rows(rows)
        assert result == [{"id": str(uid1)}, {"id": str(uid2)}]

    def test_mask_fields_propagated(self):
        rows = [{"secret": "a"}, {"secret": None}]
        result = serialize_rows(rows, mask_fields={"secret": "***"})
        assert result == [{"secret": "***"}, {"secret": None}]


# ── validation ───────────────────────────────────────────────────────────────


class TestValidateUuid:
    def test_valid_uuid(self):
        uid = str(uuid.uuid4())
        parsed, err = validate_uuid(uid)
        assert err is None
        assert isinstance(parsed, uuid.UUID)
        assert str(parsed) == uid

    def test_invalid_uuid(self):
        parsed, err = validate_uuid("not-a-uuid", "task ID")
        assert parsed is None
        assert err["status"] == "error"
        assert "task ID" in err["message"]

    def test_empty_string(self):
        parsed, err = validate_uuid("")
        assert parsed is None
        assert err is not None


# ── errors ───────────────────────────────────────────────────────────────────


class TestTruncateError:
    def test_short_message_unchanged(self):
        assert truncate_error("short") == "short"

    def test_exact_limit(self):
        msg = "x" * 200
        assert truncate_error(msg) == msg

    def test_over_limit_truncated(self):
        msg = "x" * 250
        result = truncate_error(msg)
        assert len(result) == 200
        assert result.endswith("...")

    def test_custom_limit(self):
        msg = "x" * 50
        result = truncate_error(msg, max_length=20)
        assert len(result) == 20
        assert result.endswith("...")
