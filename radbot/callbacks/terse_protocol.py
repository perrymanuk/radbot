"""Terse JSON Protocol for sub-agent → Beto token compression.

### Why

Sub-agents emit a lot of free-form prose that Beto re-renders into its own
voice. Every token of that intermediate prose is billed twice (once as
sub-agent output, once as Beto's prompt). Under the Opus 4.7 tokenizer tax
this is a large and compounding cost.

### What

When ``config:agent.terse_protocol_enabled`` is true (or the env override
``RADBOT_TERSE_PROTOCOL_ENABLED`` is set truthy), sub-agents are instructed
to format their final reply to Beto as dense JSON with two fields:

* ``summary`` — a terse, compressed narrative (the thing whose tokens we
  are trying to save).
* ``pass_through`` — an array of exact strings Beto must not paraphrase
  (tool-result dicts, UI fenced blocks like ``radbot:<kind>``, logs, IDs).

Two callbacks cooperate:

* ``terse_protocol_before_model_callback`` (PT56) — appends the protocol
  instruction to the sub-agent's ``llm_request.config.system_instruction``.
* ``terse_protocol_after_model_callback`` (PT58) — intercepts the
  sub-agent's text response, parses the JSON, and re-emits a deterministic
  markdown rendering for Beto. If parsing fails (malformed or truncated
  JSON), it strips the broken JSON markers and returns the raw inner text
  so the turn degrades gracefully instead of dumping ``{"summary":`` at
  the user.

### Why a separate file

``scope_to_current_turn.py`` trims ``llm_request.contents``; its contract
is history-level. The terse protocol operates on ``config.system_instruction``
(request side) and ``llm_response.content`` (response side). Overloading
the existing callback would blur two orthogonal concerns — reviewed and
rejected in the EX21 plan council.

### ADK compatibility

Written for ``google-adk>=2.0.0a3`` in V1 LlmAgent mode (the project
default; see ``CLAUDE.md`` for why V2 ``_Mesh`` is off). Callback
signatures match the pattern used by ``scope_to_current_turn`` and
``telemetry_callback``.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


TERSE_JSON_OPEN = "<terse_json>"
TERSE_JSON_CLOSE = "</terse_json>"

TERSE_PROTOCOL_INSTRUCTION = """\
## Output Protocol: Terse JSON

Your final reply to the orchestrator (Beto) MUST be a single JSON object
wrapped in <terse_json>...</terse_json> tags. Do not emit any text outside
those tags on your final turn.

Schema:
{
  "summary": "<one to three short sentences, data-dense, no prose filler>",
  "pass_through": ["<exact string 1>", "<exact string 2>", ...]
}

Rules:
- "summary" is the only place your own words appear. Write like a telegram,
  not like a chat reply. The orchestrator will re-hydrate it into its own
  voice, so persona / pleasantries / hedging are wasted tokens here.
- "pass_through" holds strings that must reach the user verbatim: tool
  result identifiers, exact log lines, UI fenced blocks such as
  ```radbot:card ... ``` (include the fences), URLs, IDs, quoted errors.
  When in doubt, pass through rather than summarize — paraphrasing a
  tool-generated string counts as hallucination.
- Do not emit the protocol tags on tool-call turns. They apply only to
  the final natural-language response that returns control to Beto.
- If you truly have nothing to report, emit
  <terse_json>{"summary": "", "pass_through": []}</terse_json>
  rather than an empty reply.
"""


# ── Feature flag ─────────────────────────────────────────────


def is_terse_protocol_enabled() -> bool:
    """Read the flag from ``config:agent.terse_protocol_enabled`` with an
    env override.

    Env var ``RADBOT_TERSE_PROTOCOL_ENABLED`` wins when set to one of
    ``{"1", "true", "yes", "on"}`` (case-insensitive). Otherwise we fall
    back to the DB-merged config via ``config_loader.get_agent_config()``,
    which picks up admin-UI edits after ``load_db_config()``.

    Defaults to ``False`` — the feature is strictly opt-in.
    """
    env = os.environ.get("RADBOT_TERSE_PROTOCOL_ENABLED")
    if env is not None:
        if env.strip().lower() in {"1", "true", "yes", "on"}:
            return True
        if env.strip().lower() in {"0", "false", "no", "off", ""}:
            return False
    try:
        from radbot.config.config_loader import config_loader

        agent_cfg = config_loader.get_agent_config()
        return bool(agent_cfg.get("terse_protocol_enabled", False))
    except Exception as e:
        logger.debug("is_terse_protocol_enabled: config read failed (%s)", e)
        return False


# ── Rehydration (pure, unit-testable) ────────────────────────


_TERSE_TAG_RE = re.compile(
    rf"{re.escape(TERSE_JSON_OPEN)}\s*(.*?)\s*{re.escape(TERSE_JSON_CLOSE)}",
    re.DOTALL,
)
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_BARE_JSON_RE = re.compile(r"(\{[^{}]*\"summary\"[^{}]*\})", re.DOTALL)


_TRUNCATED_DEGRADE_MARKER = "(sub-agent response was malformed or truncated)"


def _extract_terse_candidate(raw_text: str) -> Optional[str]:
    """Return the JSON candidate string, or None if no wrapper/shape found.

    Tries, in order: ``<terse_json>...</terse_json>`` tags, ```` ```json
    ... ``` ```` fences, then a bare ``{...}`` object that at least mentions
    ``"summary"``. Returning the first match keeps the function cheap and
    deterministic for tests.

    A special empty-string return (``""``) signals "saw a protocol marker
    but couldn't extract a candidate" — e.g. an unclosed ``<terse_json>``
    from a truncated response. The caller routes that to the malformed
    path so truncated output still gets its markers stripped.
    """
    m = _TERSE_TAG_RE.search(raw_text)
    if m:
        return m.group(1).strip()
    # Open tag with no close tag → truncation. Signal with "" instead of None.
    if TERSE_JSON_OPEN in raw_text and TERSE_JSON_CLOSE not in raw_text:
        return ""
    m = _JSON_FENCE_RE.search(raw_text)
    if m:
        return m.group(1).strip()
    m = _BARE_JSON_RE.search(raw_text)
    if m:
        return m.group(1).strip()
    return None


def _strip_broken_markers(raw_text: str) -> str:
    """Remove terse-protocol markers and bare JSON fences, leave the rest.

    Used on the malformed path so that the user sees the sub-agent's best
    effort without a half-open ``{"summary":`` smeared across the turn.
    """
    # Strip any complete <terse_json>...</terse_json> blocks first.
    stripped = _TERSE_TAG_RE.sub("", raw_text)
    # Then scrub stray opening/closing tags (truncation leaves these behind).
    stripped = stripped.replace(TERSE_JSON_OPEN, "")
    stripped = stripped.replace(TERSE_JSON_CLOSE, "")
    # Drop JSON code-fence markup (keep fence *contents* — they may be the
    # only remnant of the sub-agent's attempt).
    stripped = re.sub(r"```(?:json)?", "", stripped)
    stripped = stripped.replace("```", "")
    cleaned = stripped.strip()
    if cleaned:
        return cleaned
    # Nothing salvageable — don't leak raw tags, and don't return empty
    # (which would trip the empty-content retry loop). A standard marker
    # keeps the turn non-empty and gives Beto / the user a clear signal.
    return _TRUNCATED_DEGRADE_MARKER


def rehydrate_terse_payload(raw_text: str) -> str:
    """Convert a sub-agent's terse-JSON response into Beto-friendly markdown.

    On valid JSON: returns a canonical markdown block with ``Summary`` and
    (optionally) ``Pass-through`` sections. Markdown was chosen over
    re-emitting the raw JSON because (a) it composes with Beto's existing
    prompt conventions and (b) it's deterministic across model retries,
    which is what the unit test pins.

    On malformed JSON: strips the broken protocol markers and returns the
    raw inner text. The turn still shows the user *something* — worst case,
    the sub-agent's truncated prose — rather than leaking
    ``<terse_json>{"summary":`` at them.

    Empty / non-protocol input is returned untouched; the callback checks
    enablement separately so this function stays pure.
    """
    if not raw_text:
        return raw_text

    candidate = _extract_terse_candidate(raw_text)
    if candidate is None:
        # Sub-agent ignored the protocol (flag flipped mid-session, or an
        # older cached system prompt). Pass through as-is.
        return raw_text
    if candidate == "":
        # Unclosed <terse_json> — truncated mid-stream. Route to strip path
        # so the tags don't leak.
        return _strip_broken_markers(raw_text)

    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        logger.debug(
            "terse_protocol: malformed JSON (len=%d) — degrading to raw text",
            len(candidate),
        )
        return _strip_broken_markers(raw_text)

    if not isinstance(payload, dict):
        return _strip_broken_markers(raw_text)

    summary = payload.get("summary", "")
    pass_through = payload.get("pass_through", []) or []
    if not isinstance(summary, str):
        summary = str(summary)
    if not isinstance(pass_through, list):
        pass_through = []

    lines = []
    if summary.strip():
        lines.append(f"**Summary:** {summary.strip()}")
    if pass_through:
        lines.append("")
        lines.append("**Pass-through:**")
        for item in pass_through:
            lines.append(str(item))
    if not lines:
        # Valid JSON but empty both fields — tell Beto there's no content
        # without returning an empty string (which would trip the empty-
        # content callback and force a retry).
        return "(sub-agent returned empty terse payload)"
    return "\n".join(lines)


# ── ADK callbacks ────────────────────────────────────────────


def _append_to_system_instruction(llm_request: Any, text: str) -> None:
    """Append ``text`` to ``llm_request.config.system_instruction``.

    Mirrors the helper in ``radbot.tools.telos.callback`` — ADK stores the
    system instruction as ``str``, ``Content``, or ``None`` depending on
    how the agent was constructed. We normalize to string and concatenate.
    """
    config = getattr(llm_request, "config", None)
    if config is None:
        return
    existing = getattr(config, "system_instruction", None)
    if existing is None:
        config.system_instruction = text
        return
    if isinstance(existing, str):
        config.system_instruction = f"{existing}\n\n{text}"
        return
    try:
        parts = getattr(existing, "parts", None) or []
        chunks = [getattr(p, "text", "") or "" for p in parts]
        existing_text = "\n".join(c for c in chunks if c)
    except Exception:
        existing_text = ""
    config.system_instruction = f"{existing_text}\n\n{text}" if existing_text else text


def terse_protocol_before_model_callback(
    callback_context: Any,
    llm_request: Any,
) -> Optional[Any]:
    """Append the Terse JSON protocol instruction to the sub-agent's system
    prompt when the feature flag is enabled.

    Touches only ``llm_request.config.system_instruction`` — never
    ``llm_request.contents``, per EX21 Constraint 1.
    """
    try:
        if not is_terse_protocol_enabled():
            return None
        _append_to_system_instruction(llm_request, TERSE_PROTOCOL_INSTRUCTION)
    except Exception as e:
        logger.debug("terse_protocol before_model error (non-fatal): %s", e)
    return None


def _response_text_parts(llm_response: Any) -> list:
    """Return the list of Part objects on an ``LlmResponse`` that carry
    text (no function_call / function_response)."""
    content = getattr(llm_response, "content", None)
    if content is None:
        return []
    parts = getattr(content, "parts", None) or []
    text_parts = []
    for p in parts:
        if getattr(p, "function_call", None):
            return []  # mid-stream tool turn — skip rehydration entirely
        if getattr(p, "function_response", None):
            return []
        if getattr(p, "text", None):
            text_parts.append(p)
    return text_parts


def terse_protocol_after_model_callback(
    callback_context: Any,
    llm_response: Any,
) -> Optional[Any]:
    """Rehydrate a sub-agent's terse JSON reply into Beto-friendly markdown.

    No-ops unless:
      * the feature flag is enabled, AND
      * the response carries pure text (no function_call / function_response
        parts — we only transform final natural-language turns, not mid-
        stream tool calls).

    Degrades gracefully on malformed JSON via ``_strip_broken_markers``.
    Returns ``None`` — the llm_response is mutated in place, which is the
    same pattern ``handle_empty_response_after_model`` uses.
    """
    try:
        if not is_terse_protocol_enabled():
            return None
        text_parts = _response_text_parts(llm_response)
        if not text_parts:
            return None

        # Concatenate text across parts, transform once, write back to the
        # first part and blank the rest. Most sub-agent text responses are
        # a single part; multi-part text is rare but we handle it so the
        # rehydrated markdown isn't split across parts in a way Beto would
        # see as two separate messages.
        raw = "".join(getattr(p, "text", "") or "" for p in text_parts)
        rehydrated = rehydrate_terse_payload(raw)
        if rehydrated == raw:
            return None

        text_parts[0].text = rehydrated
        for p in text_parts[1:]:
            p.text = ""
    except Exception as e:
        logger.debug("terse_protocol after_model error (non-fatal): %s", e)
    return None
