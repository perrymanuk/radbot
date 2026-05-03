"""Tests for the Kideo status mapping in radbot.web.api.videos."""

import logging

import pytest

from radbot.web.api.videos import (
    _KIDEO_STATUS_MAP,
    DEFAULT_UNKNOWN_STATUS,
    _map_status,
)


class TestMapStatus:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("ready", "in_library"),
            ("available", "in_library"),
            ("downloaded", "in_library"),
            ("queued", "queued"),
            ("pending", "queued"),
            ("downloading", "processing"),
            ("transcoding", "processing"),
            ("error", "error"),
            ("failed", "error"),
            ("rejected", "error"),
            ("cancelled", "error"),
            ("expired", "error"),
        ],
    )
    def test_known_status_maps_correctly(self, raw, expected):
        assert _map_status(raw) == expected

    def test_uppercase_status_normalized(self):
        assert _map_status("QUEUED") == "queued"
        assert _map_status("Failed") == "error"

    def test_unknown_status_falls_back_to_default(self):
        assert _map_status("weird-new-state") == DEFAULT_UNKNOWN_STATUS

    def test_unknown_status_respects_explicit_default(self):
        assert _map_status("weird-new-state", default="queued") == "queued"

    def test_none_status_returns_default(self):
        assert _map_status(None) == DEFAULT_UNKNOWN_STATUS

    def test_empty_status_returns_default(self):
        assert _map_status("") == DEFAULT_UNKNOWN_STATUS

    def test_explicit_default_used_for_none(self):
        assert _map_status(None, default="queued") == "queued"

    def test_unmapped_status_logs_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="radbot.web.api.videos"):
            _map_status("weird-new-state")
        assert any(
            "Unmapped Kideo status" in r.message and "weird-new-state" in r.message
            for r in caplog.records
        )

    def test_known_status_does_not_log_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="radbot.web.api.videos"):
            _map_status("queued")
        assert not [r for r in caplog.records if "Unmapped Kideo status" in r.message]

    def test_none_does_not_log_warning(self, caplog):
        # A missing status from the provider isn't worth a WARNING for every poll.
        with caplog.at_level(logging.WARNING, logger="radbot.web.api.videos"):
            _map_status(None)
        assert not [r for r in caplog.records if "Unmapped Kideo status" in r.message]

    def test_default_unknown_status_is_unknown(self):
        # Guard against silent regression to "in_library" — the bug we're fixing.
        assert DEFAULT_UNKNOWN_STATUS == "unknown"

    def test_terminal_failure_states_are_mapped_explicitly(self):
        # All these should map to "error", not silently fall through to default.
        for failure_state in ("rejected", "cancelled", "expired", "failed", "error"):
            assert _KIDEO_STATUS_MAP.get(failure_state) == "error"
