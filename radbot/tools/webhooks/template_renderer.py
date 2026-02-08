"""
Simple template renderer for webhook prompt templates.

Supports ``{{payload.key.subkey}}`` style substitution using dot-notation
paths into the incoming JSON payload.
"""

import logging
import re
from typing import Any, Dict

logger = logging.getLogger(__name__)

_TEMPLATE_PATTERN = re.compile(r"\{\{(.*?)\}\}")


def _resolve_path(obj: Any, path: str) -> str:
    """Walk a dot-separated path into a nested dict/list and return the value as a string."""
    parts = path.strip().split(".")
    current = obj
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, (list, tuple)):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return ""
        else:
            return ""
        if current is None:
            return ""
    return str(current)


def render_template(template: str, payload: Dict[str, Any]) -> str:
    """
    Replace all ``{{path}}`` placeholders in *template* with values
    resolved from *payload*.

    Unresolvable paths are replaced with the empty string.

    Examples::

        render_template("Repo {{payload.repo.name}} pushed", {"payload": {...}})
    """
    # Wrap the raw payload under a "payload" key so templates can use
    # {{payload.x}} naturally, but also support bare {{key}}.
    context = {"payload": payload}
    context.update(payload)

    def _replace(match: re.Match) -> str:
        path = match.group(1)
        return _resolve_path(context, path)

    return _TEMPLATE_PATTERN.sub(_replace, template)
