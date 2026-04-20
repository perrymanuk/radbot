"""Unit tests for TelemetryService — fail-open semantics, no wall-clock waits.

We assert against the service module's logger (mocked) rather than pytest's
``caplog`` fixture. The radbot logging stack configures handlers at import
time and may disable propagation, leaving ``caplog`` empty in CI even when
warnings are emitted — mocking the logger sidesteps that entirely.
"""

from __future__ import annotations

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


@pytest.fixture
def warn_log():
    """Capture every warning emitted via the service module's logger."""
    with patch("radbot.tools.telemetry.service.logger") as mock_logger:
        yield mock_logger


def _warn_messages(mock_logger) -> List[str]:
    return [c.args[0] for c in mock_logger.warning.call_args_list]


def _make_service(db_writer=None, max_queue_size: int = 1000) -> TelemetryService:
    return TelemetryService(
        db_writer=db_writer or (lambda batch: None),
        max_queue_size=max_queue_size,
    )


# --------------------------------------------------------------- queue overflow


def test_enqueue_drops_when_queue_full(warn_log):
    """A full queue must drop silently with one rate-limited warning — never raise."""
    svc = _make_service(max_queue_size=2)
    # Don't start the worker — fill the queue manually so put_nowait fails.
    svc._queue.put_nowait(("dream_pass_complete", _payload()))
    svc._queue.put_nowait(("dream_pass_complete", _payload()))

    # Should not raise even though the worker is asleep and queue is full.
    with patch.object(svc, "_ensure_started"):
        svc.enqueue("dream_pass_complete", _payload())

    msgs = _warn_messages(warn_log)
    assert any("queue full" in m for m in msgs), msgs
    assert svc._queue.qsize() == 2  # third event was dropped


# ------------------------------------------------------------------ DB timeout


def test_db_timeout_drops_batch(warn_log):
    """A db_writer raising OperationalError must NOT propagate; batch is dropped."""
    def boom(batch):
        raise psycopg2.OperationalError("statement timeout (mocked, no real wait)")

    svc = _make_service(db_writer=boom)
    batch: List[Tuple[str, Dict[str, Any]]] = [
        ("dream_pass_complete", _payload()),
        ("dream_pass_complete", _payload()),
    ]

    # _flush_batch is the post-collect tight loop; calling it directly avoids
    # spawning the worker thread (no sleep, no race).
    svc._flush_batch(batch)

    msgs = _warn_messages(warn_log)
    assert any("DB write failed" in m for m in msgs), msgs


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


def test_pydantic_rejects_extra_text_field(warn_log):
    """Extra string fields like ``"text"`` must be dropped (PII safety)."""
    svc = _make_service()
    payload = dict(_payload())
    payload["text"] = "user typed something private here"

    svc.enqueue("dream_pass_complete", payload)

    assert svc._queue.qsize() == 0
    msgs = _warn_messages(warn_log)
    assert any("validation failed" in m for m in msgs), msgs


def test_pydantic_rejects_unknown_event_type(warn_log):
    svc = _make_service()
    svc.enqueue("not_a_real_event", {"x": 1})
    assert svc._queue.qsize() == 0
    msgs = _warn_messages(warn_log)
    assert any("validation failed" in m for m in msgs), msgs


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


def test_warn_throttle_suppresses_repeated_warnings(warn_log):
    svc = _make_service(max_queue_size=1)
    svc._queue.put_nowait(("dream_pass_complete", _payload()))

    with patch.object(svc, "_ensure_started"):
        svc.enqueue("dream_pass_complete", _payload())  # warns
        svc.enqueue("dream_pass_complete", _payload())  # throttled

    warns = [m for m in _warn_messages(warn_log) if "queue full" in m]
    assert len(warns) == 1, _warn_messages(warn_log)
