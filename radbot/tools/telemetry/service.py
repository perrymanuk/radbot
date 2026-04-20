"""Decoupled, fail-open TelemetryService.

Producers call ``enqueue(event_type, payload)`` and return immediately. A
background worker thread validates each event against a strict Pydantic
model (text fields are rejected as PII) and batch-inserts to Postgres
with hard 1-second connect + statement timeouts. Any failure path drops
the event with a rate-limited warning — telemetry must never break the
caller.

Lifecycle: ``start()`` is lazy on first enqueue. ``flush(timeout=3.0)``
joins the worker after draining outstanding events; an ``atexit`` hook
runs it on process exit.
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import queue
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import psycopg2

logger = logging.getLogger(__name__)

QUEUE_MAX_SIZE = 1000
BATCH_MAX_SIZE = 50
WORKER_POLL_TIMEOUT_S = 1.0
DB_CONNECT_TIMEOUT_S = 1
DB_STATEMENT_TIMEOUT_MS = 1000
FLUSH_TIMEOUT_S = 3.0
WARN_THROTTLE_S = 60.0

_SHUTDOWN = object()  # sentinel pushed by flush() to wake the worker


def _telemetry_enabled() -> bool:
    """Read the kill-switch from ``config:telemetry.enabled`` (default True)."""
    try:
        from radbot.config.config_loader import config_loader

        section = config_loader.get_config().get("telemetry") or {}
        if isinstance(section, dict):
            return bool(section.get("enabled", True))
        return True
    except Exception:
        return True


def _db_dsn_kwargs() -> Dict[str, Any]:
    """Resolve Postgres connection kwargs from config + env (mirrors db.connection)."""
    from radbot.config import config_loader

    cfg = config_loader.get_config().get("database", {}) or {}
    return dict(
        database=cfg.get("db_name") or os.getenv("POSTGRES_DB"),
        user=cfg.get("user") or os.getenv("POSTGRES_USER"),
        password=cfg.get("password") or os.getenv("POSTGRES_PASSWORD"),
        host=cfg.get("host") or os.getenv("POSTGRES_HOST", "localhost"),
        port=cfg.get("port") or os.getenv("POSTGRES_PORT", "5432"),
        connect_timeout=DB_CONNECT_TIMEOUT_S,
    )


def _default_db_writer(batch: List[Tuple[str, Dict[str, Any]]]) -> None:
    """Open a short-lived connection with strict timeouts and insert ``batch``.

    Raises on any DB error; the caller is responsible for fail-open semantics.
    """
    conn = psycopg2.connect(**_db_dsn_kwargs())
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(f"SET statement_timeout = {DB_STATEMENT_TIMEOUT_MS}")
                cur.executemany(
                    "INSERT INTO telemetry_events (event_type, payload) VALUES (%s, %s)",
                    [(et, json.dumps(p)) for et, p in batch],
                )
    finally:
        try:
            conn.close()
        except Exception:
            pass


class TelemetryService:
    """Singleton-style telemetry pipeline. See module docstring."""

    def __init__(
        self,
        *,
        db_writer: Optional[Callable[[List[Tuple[str, Dict[str, Any]]]], None]] = None,
        max_queue_size: int = QUEUE_MAX_SIZE,
    ) -> None:
        self._queue: "queue.Queue[Any]" = queue.Queue(maxsize=max_queue_size)
        self._db_writer = db_writer or _default_db_writer
        self._worker: Optional[threading.Thread] = None
        self._start_lock = threading.Lock()
        self._stopping = threading.Event()
        # None sentinel (not 0.0): on Linux `time.monotonic()` is seconds
        # since boot, which on a freshly-booted CI runner can be < 60, so
        # `now - 0.0 < WARN_THROTTLE_S` would silently throttle the very
        # first warning. `None` means "never warned yet — always log".
        self._last_warn_at: Optional[float] = None
        self._warn_lock = threading.Lock()

    # ------------------------------------------------------------------ public

    def enqueue(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Validate + enqueue. Never raises. Drops on QueueFull or kill-switch."""
        if not _telemetry_enabled():
            return
        try:
            from .models import validate_payload

            clean = validate_payload(event_type, payload)
        except Exception as e:
            self._warn_throttled(
                f"telemetry: dropped {event_type!r} — payload validation failed: {e}"
            )
            return

        self._ensure_started()
        try:
            self._queue.put_nowait((event_type, clean))
        except queue.Full:
            self._warn_throttled(
                f"telemetry: dropped {event_type!r} — queue full ({self._queue.maxsize})"
            )

    def flush(self, timeout: float = FLUSH_TIMEOUT_S) -> None:
        """Signal the worker to drain + exit, then join with ``timeout``."""
        worker = self._worker
        if worker is None or not worker.is_alive():
            return
        self._stopping.set()
        try:
            self._queue.put_nowait(_SHUTDOWN)
        except queue.Full:
            pass  # worker will see _stopping on its next poll
        worker.join(timeout=timeout)

    # ----------------------------------------------------------------- internal

    def _ensure_started(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        with self._start_lock:
            if self._worker is not None and self._worker.is_alive():
                return
            self._stopping.clear()
            t = threading.Thread(
                target=self._run, name="telemetry-worker", daemon=True
            )
            t.start()
            self._worker = t

    def _run(self) -> None:
        while True:
            batch = self._collect_batch()
            if batch:
                self._flush_batch(batch)
            if self._stopping.is_set() and self._queue.empty():
                return

    def _collect_batch(self) -> List[Tuple[str, Dict[str, Any]]]:
        """Block up to ``WORKER_POLL_TIMEOUT_S`` for the first item, then drain."""
        batch: List[Tuple[str, Dict[str, Any]]] = []
        try:
            first = self._queue.get(timeout=WORKER_POLL_TIMEOUT_S)
        except queue.Empty:
            return batch
        if first is _SHUTDOWN:
            return batch
        batch.append(first)
        while len(batch) < BATCH_MAX_SIZE:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if item is _SHUTDOWN:
                break
            batch.append(item)
        return batch

    def _flush_batch(self, batch: List[Tuple[str, Dict[str, Any]]]) -> None:
        try:
            self._db_writer(batch)
        except Exception as e:
            self._warn_throttled(
                f"telemetry: dropped batch of {len(batch)} — DB write failed: {e}"
            )

    def _warn_throttled(self, msg: str) -> None:
        now = time.monotonic()
        with self._warn_lock:
            if (
                self._last_warn_at is not None
                and now - self._last_warn_at < WARN_THROTTLE_S
            ):
                return
            self._last_warn_at = now
        logger.warning(msg)


# --------------------------------------------------------------------- singleton

_service: Optional[TelemetryService] = None
_service_lock = threading.Lock()
_atexit_registered = False


def get_telemetry_service() -> TelemetryService:
    """Return the process-wide TelemetryService, creating it on first call."""
    global _service, _atexit_registered
    if _service is not None:
        return _service
    with _service_lock:
        if _service is not None:
            return _service
        _service = TelemetryService()
        if not _atexit_registered:
            atexit.register(_atexit_flush)
            _atexit_registered = True
        return _service


def reset_telemetry_service() -> None:
    """Test/admin helper: flush + drop the singleton so the next call rebuilds it."""
    global _service
    with _service_lock:
        if _service is not None:
            try:
                _service.flush()
            except Exception:
                pass
        _service = None


def _atexit_flush() -> None:
    svc = _service
    if svc is None:
        return
    try:
        svc.flush()
    except Exception:
        pass
