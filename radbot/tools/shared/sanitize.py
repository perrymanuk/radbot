"""
Unicode sanitization for prompt injection defense.

Strips invisible and control Unicode characters that can be used to smuggle
instructions past human review into LLM inputs.  Three strictness levels
are provided (relaxed, standard, strict) and the module is designed to be
called both per-tool (explicit defense) and from a before_model_callback
(catch-all).  Sanitization is idempotent, so double-processing is safe.

Character categories stripped:
  - Zero-width characters (U+200B, U+200C, U+200D, U+FEFF, U+2063, U+2064)
  - Bidirectional controls (U+202A-202E, U+2066-2069)
  - Unicode tag characters (U+E0000-E007F)
  - Control characters (U+0000-001F excl tab/newline/cr, U+007F-009F)
  - Soft hyphen (U+00AD)
  - Variation selectors (U+FE00-FE0F)
  - Interlinear annotations (U+FFF9-FFFB)
  - (strict only) Private Use Area (U+E000-F8FF)
"""

import logging
import unicodedata
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Character sets
# ---------------------------------------------------------------------------

_ZERO_WIDTH: Set[int] = {
    0x200B,  # Zero Width Space
    0x200C,  # Zero Width Non-Joiner
    0x200D,  # Zero Width Joiner
    0xFEFF,  # BOM / Zero Width No-Break Space
    0x2063,  # Invisible Separator
    0x2064,  # Invisible Plus
}

_BIDI_CONTROLS: Set[int] = set(range(0x202A, 0x202F)) | set(range(0x2066, 0x206A))

_TAG_CHARS: Set[int] = set(range(0xE0000, 0xE0080))

# C0 controls minus tab (0x09), newline (0x0A), carriage return (0x0D)
_CONTROL_CHARS: Set[int] = (set(range(0x0000, 0x0020)) - {0x09, 0x0A, 0x0D}) | set(
    range(0x007F, 0x00A0)
)

_SOFT_HYPHEN: Set[int] = {0x00AD}

_VARIATION_SELECTORS: Set[int] = set(range(0xFE00, 0xFE10))

_INTERLINEAR: Set[int] = {0xFFF9, 0xFFFA, 0xFFFB}

_PUA: Set[int] = set(range(0xE000, 0xF900))

# Pre-built strip sets per strictness level (cached at module load)
_RELAXED_SET: frozenset = frozenset(
    _ZERO_WIDTH | _BIDI_CONTROLS | _TAG_CHARS | _CONTROL_CHARS
)
_STANDARD_SET: frozenset = frozenset(
    _RELAXED_SET | _SOFT_HYPHEN | _VARIATION_SELECTORS | _INTERLINEAR
)
_STRICT_SET: frozenset = frozenset(_STANDARD_SET | _PUA)

_STRIP_SETS = {
    "relaxed": _RELAXED_SET,
    "standard": _STANDARD_SET,
    "strict": _STRICT_SET,
}


# ---------------------------------------------------------------------------
# Config helper
# ---------------------------------------------------------------------------


def _get_sanitize_config() -> Dict[str, Any]:
    """Load sanitization config from the config system.

    Returns sensible defaults when the config system is unavailable.
    """
    defaults: Dict[str, Any] = {
        "enabled": True,
        "strictness": "standard",
        "log_detections": True,
        "callback_enabled": True,
    }
    try:
        from radbot.config.config_loader import config_loader

        security_cfg = config_loader.get_config().get("security", {})
        sanitize_cfg = security_cfg.get("sanitize", {})
        # Merge with defaults
        for key in defaults:
            if key in sanitize_cfg:
                defaults[key] = sanitize_cfg[key]
    except Exception:
        pass  # Config unavailable – use defaults
    return defaults


# ---------------------------------------------------------------------------
# Core sanitization
# ---------------------------------------------------------------------------


def sanitize_text(
    text: str,
    source: str = "unknown",
    strictness: Optional[str] = None,
) -> str:
    """Normalize and strip dangerous invisible characters from *text*.

    1. NFKC normalization (collapses fullwidth chars, ligatures, etc.)
    2. Strip characters in the selected danger set.

    Args:
        text: The input string.
        source: Label for log attribution (e.g. "gmail", "webhook").
        strictness: One of "relaxed", "standard", "strict".
                    ``None`` reads from config (default: "standard").

    Returns:
        Sanitized string.
    """
    if not text:
        return text

    cfg = _get_sanitize_config()
    if not cfg["enabled"]:
        return text

    if strictness is None:
        strictness = cfg["strictness"]

    strip_set = _STRIP_SETS.get(strictness, _STANDARD_SET)

    # Step 1: NFKC normalization
    normalized = unicodedata.normalize("NFKC", text)

    # Step 2: strip dangerous codepoints
    cleaned = "".join(ch for ch in normalized if ord(ch) not in strip_set)

    # Logging
    if cleaned != normalized and cfg.get("log_detections", True):
        removed_count = len(normalized) - len(cleaned)
        logger.warning(
            "sanitize[%s]: stripped %d invisible/control character(s) "
            "(strictness=%s, input_len=%d)",
            source,
            removed_count,
            strictness,
            len(text),
        )

    return cleaned


def sanitize_dict(
    data: Dict[str, Any],
    source: str = "unknown",
    strictness: Optional[str] = None,
    keys: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Recursively sanitize string values in a dictionary.

    Args:
        data: The dictionary to sanitize.
        source: Label for log attribution.
        strictness: Strictness level override.
        keys: If provided, only sanitize these top-level keys.
              Nested dicts are always fully sanitized.

    Returns:
        A new dictionary with sanitized string values.
    """
    if not isinstance(data, dict):
        return data

    result = {}
    for k, v in data.items():
        if keys and k not in keys:
            result[k] = v
            continue
        result[k] = _sanitize_value(v, source, strictness)
    return result


def sanitize_external_content(
    content: Any,
    source: str = "unknown",
    strictness: Optional[str] = None,
) -> Any:
    """Top-level dispatcher that sanitizes strings, dicts, and lists.

    Args:
        content: The content to sanitize (str, dict, list, or pass-through).
        source: Label for log attribution.
        strictness: Strictness level override.

    Returns:
        Sanitized content of the same type.
    """
    return _sanitize_value(content, source, strictness)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _sanitize_value(value: Any, source: str, strictness: Optional[str]) -> Any:
    """Recursively sanitize a value."""
    if isinstance(value, str):
        return sanitize_text(value, source=source, strictness=strictness)
    if isinstance(value, dict):
        return {k: _sanitize_value(v, source, strictness) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(item, source, strictness) for item in value]
    return value
