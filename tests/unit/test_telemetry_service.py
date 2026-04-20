"""Unit tests for TelemetryService — fail-open semantics, no wall-clock waits.

We exercise the service's public surface (``enqueue`` + ``flush``) and the
internal ``_flush_batch`` directly so we can assert DB-error handling
without spinning up a real worker thread or sleeping.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple
from unittest.mock import patch

import psycopg2
import pytest

from radbot.tools.telemetry.service import TelemetryService


def _payload() -> Dict[str, Any]:
    return {
        "scanned": 10,
        "clusters": 3,
        "consolidated": 2,
        "archived": 4,
        "skipped_low_trust": 1,
        "promotion_candidates": 0,
    }


@pytest.fixture(autouse=True)
def _telemetry_enabled():
    """Force the kill-switch ON for every test (default behavior anyway)."""
    with patch(
        "radbot.tools.telemetry.service._telemetry_enabled", return_value=True
    ) as m:
        yield m


def _make_service(db_writer=None, max_queue_size: int = 1000) -> TelemetryService:
    return TelemetryService(
        db_writer=db_writer or (lambda batch: None),
        max_queue_size=max_queue_size,
    )


# --------------------------------------------------------------- queue overflow


def test_enqueue_drops_when_queue_full(caplog):
    """A full queue must drop silently with one rate-limited warning — never raise."""
    svc = _make_service(max_queue_size=2)
    # Don't start the worker — fill the queue manually so put_nowait fails.
    svc._queue.put_nowait(("dream_pass_complete", _payload()))
    svc._queue.put_nowait(("dream_pass_complete", _payload()))

    with caplog.at_level(logging.WARNING, logger="radbot.tools.telemetry.service"):
        # Should not raise even though the worker is asleep and queue is full.
        with patch.object(svc, "_ensure_started"):
            svc.enqueue("dream_pass_complete", _payload())

    assert any("queue full" in r.message for r in caplog.records)
    assert svc._queue.qsize() == 2  # third event was dropped


# ------------------------------------------------------------------ DB timeout


def test_db_timeout_drops_batch(caplog):
    """A db_writer raising OperationalError must NOT propagate; batch is dropped."""
    def boom(batch):
        raise psycopg2.OperationalError("statement timeout (mocked, no real wait)")

    svc = _make_service(db_writer=boom)
    batch: List[Tuple[str, Dict[str, Any]]] = [
        ("dream_pass_complete", _payload()),
        ("dream_pass_complete", _payload()),
    ]

    with caplog.at_level(logging.WARNING, logger="radbot.tools.telemetry.service"):
        # _flush_batch is the post-collect tight loop; calling it directly
        # avoids spawning the worker thread (no sleep, no race).
        svc._flush_batch(batch)

    assert any("DB write failed" in r.message for r in caplog.records)


# ------------------------------------------------------------------ kill switch


def test_kill_switch_disables_enqueue(_telemetry_enabled):
    """``enabled=False`` must short-circuit before validation or queue access."""
    _telemetry_enabled.return_value = False
    svc = _make_service()
    with patch.object(svc, "_ensure_started") as ensure:
        svc.enqueue("dream_pass_complete", _payload())
    assert svc._queue.qsize() == 0
    ensure.assert_not_called()


# ----------------------------------------------------- pydantic strips PII text


def test_pydantic_rejects_extra_text_field(caplog):
    """Extra string fields like ``"text"`` must be dropped (PII safety)."""
    svc = _make_service()
    payload = dict(_payload())
    payload["text"] = "user typed something private here"

    with caplog.at_level(logging.WARNING, logger="radbot.tools.telemetry.service"):
        svc.enqueue("dream_pass_complete", payload)

    assert svc._queue.qsize() == 0
    assert any("validation failed" in r.message for r in caplog.records)


def test_pydantic_rejects_unknown_event_type(caplog):
    svc = _make_service()
    with caplog.at_level(logging.WARNING, logger="radbot.tools.telemetry.service"):
        svc.enqueue("not_a_real_event", {"x": 1})
    assert svc._queue.qsize() == 0
    assert any("validation failed" in r.message for r in caplog.records)


# ---------------------------------------------------- successful happy-path enqueue


def test_valid_enqueue_lands_clean_payload_in_queue():
    svc = _make_service()
    with patch.object(svc, "_ensure_started"):
        svc.enqueue("dream_pass_complete", _payload())
    assert svc._queue.qsize() == 1
    event_type, clean = svc._queue.get_nowait()
    assert event_type == "dream_pass_complete"
    assert clean == _payload()
    assert "text" not in clean


# -------------------------------------------------------------- flush drains


def test_flush_drains_queue_via_real_worker():
    """End-to-end: enqueue N, flush, assert the mocked DB writer saw all N."""
    seen: List[Tuple[str, Dict[str, Any]]] = []

    def writer(batch):
        seen.extend(batch)

    svc = _make_service(db_writer=writer)
    for _ in range(5):
        svc.enqueue("dream_pass_complete", _payload())

    svc.flush(timeout=5.0)

    assert len(seen) == 5
    assert all(et == "dream_pass_complete" for et, _ in seen)


def test_flush_is_safe_when_worker_never_started():
    svc = _make_service()
    svc.flush(timeout=0.1)  # no-op, must not raise


# ------------------------------------------------------------- warn throttling


def test_warn_throttle_suppresses_repeated_warnings(caplog):
    svc = _make_service(max_queue_size=1)
    svc._queue.put_nowait(("dream_pass_complete", _payload()))

    with caplog.at_level(logging.WARNING, logger="radbot.tools.telemetry.service"):
        with patch.object(svc, "_ensure_started"):
            svc.enqueue("dream_pass_complete", _payload())  # warns
            svc.enqueue("dream_pass_complete", _payload())  # throttled

    warns = [r for r in caplog.records if "queue full" in r.message]
    assert len(warns) == 1
