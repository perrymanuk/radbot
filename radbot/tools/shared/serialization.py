"""Shared serialization helpers for DB rows containing UUIDs and datetimes."""

import uuid
from typing import Any, Dict, List, Optional


def serialize_row(
    row: Dict[str, Any],
    *,
    mask_fields: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Convert a DB row dict, coercing UUIDs/datetimes.

    Args:
        row: A dict (typically from a RealDictCursor).
        mask_fields: Mapping of field_name -> replacement value.
            Truthy fields get the replacement; falsy keep None.

    Returns:
        A new dict safe for JSON serialization.
    """
    mask_fields = mask_fields or {}
    item: Dict[str, Any] = {}
    for k, v in row.items():
        if k in mask_fields:
            item[k] = mask_fields[k] if v else None
        elif isinstance(v, uuid.UUID):
            item[k] = str(v)
        elif hasattr(v, "isoformat"):
            item[k] = v.isoformat()
        else:
            item[k] = v
    return item


def serialize_rows(
    rows: List[Dict[str, Any]],
    *,
    mask_fields: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Convert a list of DB row dicts. See :func:`serialize_row`."""
    return [serialize_row(r, mask_fields=mask_fields) for r in rows]
