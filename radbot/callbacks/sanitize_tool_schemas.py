"""Before-model callback that removes non-standard JSON-Schema keys from
outgoing tool declarations.

### Why

Gemini's model API (as of 2026-04) rejects requests whose
``tools[*].function_declarations[*].parameters`` contain the snake_case
key ``additional_properties``::

    Invalid JSON payload received. Unknown name "additional_properties"
    at 'tools[0].function_declarations[1].parameters.properties[5]
                .value.any_of[0]': Cannot find field.

The standard JSON-Schema keyword is ``additionalProperties`` (camelCase).
Pydantic v2 emits that correctly, but somewhere in the
Pydantic→Schema-proto→JSON pipeline (google-genai side), the field gets
copied into the proto as its snake_case python attribute name and leaks
back into the REST body. The gemini-2.5 / gemini-3.1-flash validators
surface this strictly; gemini-3.1-pro used to tolerate it silently, so
the failure began after the recent main-agent model downgrade (see
``docs/implementation/integrations/ha_mcp_migration.md`` and beto's
flash move in commit ``784e398``).

### What

This callback walks ``llm_request.config.tools`` and recursively strips
the offending keys from every ``parameters`` schema. ``additionalProperties``
(camelCase, standards-compliant) is left alone; only the non-standard
snake_case version is removed. Applied on every agent's
``before_model_callback`` so the scrub runs for every LLM call,
regardless of which tool module introduced the leak.

Idempotent and failure-safe: if anything about the Schema structure is
different from what we expect, the callback swallows the exception and
returns — telemetry will still capture the upstream error.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


# Keys that Gemini rejects when it sees them in a parameters schema.
# Extend this set conservatively if similar schema-drift bugs surface.
_NON_STANDARD_SCHEMA_KEYS = ("additional_properties",)


def _scrub_obj(obj: Any) -> None:
    """Recursively remove non-standard keys from a Schema-like object.

    Handles two representations interchangeably:
      * Python dicts (JSON-schema style)
      * google-genai Schema proto messages (attribute access)

    In both cases we walk common schema-tree fields: ``properties``,
    ``items``, ``any_of`` / ``anyOf``, ``one_of`` / ``oneOf``,
    ``all_of`` / ``allOf``.
    """
    if obj is None:
        return

    # Dict form
    if isinstance(obj, dict):
        for key in _NON_STANDARD_SCHEMA_KEYS:
            obj.pop(key, None)
        for child_key in (
            "properties",
            "items",
            "any_of",
            "anyOf",
            "one_of",
            "oneOf",
            "all_of",
            "allOf",
        ):
            child = obj.get(child_key)
            if isinstance(child, dict):
                for v in child.values():
                    _scrub_obj(v)
            elif isinstance(child, list):
                for v in child:
                    _scrub_obj(v)
        return

    # Proto / object form — remove attributes by setting them to None so
    # the serializer drops them. Try/except because proto field sets can
    # be strict about types.
    for key in _NON_STANDARD_SCHEMA_KEYS:
        if hasattr(obj, key):
            try:
                setattr(obj, key, None)
            except Exception:
                pass
    for child_key in ("properties", "items", "any_of", "one_of", "all_of"):
        child = getattr(obj, child_key, None)
        if child is None:
            continue
        # Properties can be a dict-like or repeated field of entries
        if isinstance(child, dict):
            for v in child.values():
                _scrub_obj(v)
        elif hasattr(child, "values"):
            try:
                for v in child.values():
                    _scrub_obj(v)
            except Exception:
                pass
        elif isinstance(child, (list, tuple)):
            for v in child:
                _scrub_obj(v)
        else:
            # Single nested schema
            _scrub_obj(child)


def sanitize_tool_schemas_before_model(
    callback_context: Any,
    llm_request: Any,
) -> Optional[Any]:
    """Strip ``additional_properties`` from every tool parameter schema.

    Returns ``None`` so the sanitized request proceeds unmodified in all
    other respects.
    """
    try:
        config = getattr(llm_request, "config", None)
        tools = getattr(config, "tools", None) if config is not None else None
        if not tools:
            return None

        scrubbed = 0
        for tool in tools:
            decls = getattr(tool, "function_declarations", None)
            if not decls:
                continue
            for decl in decls:
                params = getattr(decl, "parameters", None)
                if params is None:
                    continue
                _scrub_obj(params)
                scrubbed += 1

        if scrubbed:
            logger.debug(
                "sanitize-tool-schemas: processed %d function declarations",
                scrubbed,
            )
    except Exception as e:
        # Never take the request down for a schema-scrub failure — the
        # upstream call will surface any real problem with its own
        # diagnostics.
        logger.debug("sanitize-tool-schemas error (non-fatal): %s", e)
    return None
