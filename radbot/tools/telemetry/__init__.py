"""Telemetry: decoupled, fail-open metric capture for radbot.

Producers call ``get_telemetry_service().enqueue(event_type, payload)`` and
return immediately. A background worker validates payloads with strict
Pydantic models (stripping anything not whitelisted) and batch-inserts to
Postgres with strict 1s timeouts. Queue overflow or DB failure drops the
event with a rate-limited warning — telemetry must never break the caller.

Kill-switch: ``config:telemetry.enabled`` (default ``True``).

PT30 / EX7 — Semantic Distillation Baseline.
"""

from .db import init_telemetry_schema
from .service import (
    TelemetryService,
    get_telemetry_service,
    reset_telemetry_service,
)

__all__ = [
    "init_telemetry_schema",
    "TelemetryService",
    "get_telemetry_service",
    "reset_telemetry_service",
]
