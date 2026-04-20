"""Strict Pydantic payload models for telemetry events.

Every model uses ``extra="forbid"`` and integer/bool-only fields. Any
extra key (including ``"text"``, ``"prompt"``, free-form strings) raises
``ValidationError`` — the service catches it and drops the event. This
guarantees no PII or raw conversation content ever reaches Postgres.
"""

from __future__ import annotations

from typing import Any, Dict, Type

from pydantic import BaseModel, ConfigDict


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class DreamMetrics(_StrictModel):
    scanned: int
    clusters: int
    consolidated: int
    archived: int
    skipped_low_trust: int
    promotion_candidates: int


class ContextInjectionMetrics(_StrictModel):
    anchor_tokens: int
    full_block_tokens: int
    total_tokens: int
    is_first_turn: bool


EVENT_MODELS: Dict[str, Type[_StrictModel]] = {
    "dream_pass_complete": DreamMetrics,
    "context_injection": ContextInjectionMetrics,
}


def validate_payload(event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate ``payload`` against the model registered for ``event_type``.

    Raises:
        KeyError: if no model is registered for the event type.
        pydantic.ValidationError: if the payload contains extra keys or
            wrong-typed values (this is the PII strip).
    """
    model = EVENT_MODELS[event_type]
    return model.model_validate(payload).model_dump()
