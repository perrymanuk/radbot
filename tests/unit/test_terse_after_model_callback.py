"""Unit tests for the Terse JSON Protocol after_model callback and its
pure ``rehydrate_terse_payload`` helper.

Deterministic and Python-level — no LLM in the loop. The callback's valid
path is exercised via the helper (same code path); the LlmResponse mutation
path is covered with lightweight stand-ins so we don't pull in ADK's model
types just to assert on ``part.text``.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from radbot.callbacks.terse_protocol import (
    TERSE_JSON_CLOSE,
    TERSE_JSON_OPEN,
    is_terse_protocol_enabled,
    rehydrate_terse_payload,
    terse_protocol_after_model_callback,
)

# ── rehydrate_terse_payload: valid JSON ───────────────────────────────────


class TestRehydrateValidPayloads:
    def test_rehydrate_wrapped_in_terse_tags_returns_markdown(self):
        raw = (
            f"{TERSE_JSON_OPEN}"
            '{"summary": "Light kitchen is off.", "pass_through": []}'
            f"{TERSE_JSON_CLOSE}"
        )
        out = rehydrate_terse_payload(raw)
        assert "**Summary:** Light kitchen is off." in out
        assert TERSE_JSON_OPEN not in out
        assert "Pass-through" not in out  # empty pass_through → no section

    def test_rehydrate_passes_through_exact_strings_verbatim(self):
        raw = (
            f"{TERSE_JSON_OPEN}"
            '{"summary": "Found 3 entities.", '
            '"pass_through": ["light.kitchen: on", "light.bedroom: off"]}'
            f"{TERSE_JSON_CLOSE}"
        )
        out = rehydrate_terse_payload(raw)
        assert "**Summary:** Found 3 entities." in out
        assert "**Pass-through:**" in out
        assert "light.kitchen: on" in out
        assert "light.bedroom: off" in out

    def test_rehydrate_accepts_json_fenced_block(self):
        raw = (
            "Sure thing.\n\n```json\n"
            '{"summary": "Done.", "pass_through": ["id=42"]}\n'
            "```\n"
        )
        out = rehydrate_terse_payload(raw)
        assert "**Summary:** Done." in out
        assert "id=42" in out

    def test_rehydrate_accepts_bare_json_object_with_summary(self):
        raw = '{"summary": "Bare form works.", "pass_through": []}'
        out = rehydrate_terse_payload(raw)
        assert "**Summary:** Bare form works." in out

    def test_rehydrate_empty_both_fields_emits_nonempty_marker(self):
        # Empty string output would trip the empty-content callback into a
        # retry loop, so we require a non-empty placeholder.
        raw = (
            f'{TERSE_JSON_OPEN}{{"summary": "", "pass_through": []}}{TERSE_JSON_CLOSE}'
        )
        out = rehydrate_terse_payload(raw)
        assert out.strip() != ""


# ── rehydrate_terse_payload: malformed / degrade gracefully ──────────────


class TestRehydrateMalformedDegradeGracefully:
    def test_truncated_json_returns_stripped_raw_text(self):
        # Model hit max_output_tokens mid-JSON — the classic failure mode.
        raw = (
            f"{TERSE_JSON_OPEN}"
            '{"summary": "This was going to say something long but got cut off '
        )
        out = rehydrate_terse_payload(raw)
        # No leaking tags or half-open braces dumped at the user.
        assert TERSE_JSON_OPEN not in out
        assert TERSE_JSON_CLOSE not in out
        # The inner text (even broken) is still surfaced so the user gets
        # *something* rather than a mystery empty turn.
        assert "summary" in out or "cut off" in out

    def test_malformed_json_fence_returns_text_without_fence(self):
        raw = 'Sorry:\n\n```json\n{"summary": "oops", broken}\n```'
        out = rehydrate_terse_payload(raw)
        assert "```" not in out
        assert "Sorry" in out  # prose envelope preserved

    def test_non_protocol_text_passes_through_unchanged(self):
        # Sub-agent ignored the protocol entirely (flag flipped mid-session,
        # stale cached system prompt, etc.). Must not mangle the reply.
        raw = "Hey, totally gnarly — the lights are all off, my dude."
        out = rehydrate_terse_payload(raw)
        assert out == raw

    def test_json_with_non_dict_root_degrades_gracefully(self):
        # Valid JSON, wrong shape (array instead of object with summary).
        raw = f'{TERSE_JSON_OPEN}["not", "an", "object"]{TERSE_JSON_CLOSE}'
        out = rehydrate_terse_payload(raw)
        # The _BARE_JSON_RE only fires on objects containing "summary", and
        # the tag extractor will hand json.loads a list — which parses but
        # is rejected by the isinstance(dict) check, producing a stripped
        # fallback.
        assert TERSE_JSON_OPEN not in out
        assert TERSE_JSON_CLOSE not in out

    def test_empty_input_returns_empty(self):
        assert rehydrate_terse_payload("") == ""


# ── terse_protocol_after_model_callback: flag + LlmResponse shape ────────


def _mk_response(text: str, *, function_call=False):
    """Build a minimal stand-in for ``google.adk.models.LlmResponse``.

    We only touch ``response.content.parts[*].text``, so a SimpleNamespace
    tree with the right attribute shape is enough — no need to import ADK.
    """
    part = SimpleNamespace(
        text=text,
        function_call=SimpleNamespace() if function_call else None,
        function_response=None,
    )
    return SimpleNamespace(content=SimpleNamespace(parts=[part]))


class TestAfterModelCallbackRespectsFlag:
    def test_callback_noop_when_flag_disabled(self):
        raw = (
            f'{TERSE_JSON_OPEN}{{"summary": "x", "pass_through": []}}{TERSE_JSON_CLOSE}'
        )
        resp = _mk_response(raw)
        with patch(
            "radbot.callbacks.terse_protocol.is_terse_protocol_enabled",
            return_value=False,
        ):
            assert terse_protocol_after_model_callback(None, resp) is None
        # Text untouched.
        assert resp.content.parts[0].text == raw

    def test_callback_rehydrates_when_flag_enabled(self):
        raw = f'{TERSE_JSON_OPEN}{{"summary": "hi", "pass_through": []}}{TERSE_JSON_CLOSE}'
        resp = _mk_response(raw)
        with patch(
            "radbot.callbacks.terse_protocol.is_terse_protocol_enabled",
            return_value=True,
        ):
            terse_protocol_after_model_callback(None, resp)
        assert "**Summary:** hi" in resp.content.parts[0].text
        assert TERSE_JSON_OPEN not in resp.content.parts[0].text

    def test_callback_skips_function_call_turns(self):
        # Mid-stream tool call — rehydration must not fire, since the
        # protocol applies only to the final natural-language turn.
        resp = _mk_response("irrelevant", function_call=True)
        with patch(
            "radbot.callbacks.terse_protocol.is_terse_protocol_enabled",
            return_value=True,
        ):
            terse_protocol_after_model_callback(None, resp)
        assert resp.content.parts[0].text == "irrelevant"

    def test_callback_handles_missing_content_gracefully(self):
        resp = SimpleNamespace(content=None)
        with patch(
            "radbot.callbacks.terse_protocol.is_terse_protocol_enabled",
            return_value=True,
        ):
            # Must not raise.
            assert terse_protocol_after_model_callback(None, resp) is None


# ── is_terse_protocol_enabled: env override precedence ────────────────────


class TestFlagResolution:
    @pytest.mark.parametrize("value", ["1", "true", "True", "yes", "on"])
    def test_env_truthy_values_enable(self, monkeypatch, value):
        monkeypatch.setenv("RADBOT_TERSE_PROTOCOL_ENABLED", value)
        assert is_terse_protocol_enabled() is True

    @pytest.mark.parametrize("value", ["0", "false", "no", "off"])
    def test_env_falsy_values_disable_even_if_config_true(self, monkeypatch, value):
        monkeypatch.setenv("RADBOT_TERSE_PROTOCOL_ENABLED", value)
        with patch(
            "radbot.config.config_loader.config_loader.get_agent_config",
            return_value={"terse_protocol_enabled": True},
        ):
            assert is_terse_protocol_enabled() is False

    def test_falls_back_to_config_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("RADBOT_TERSE_PROTOCOL_ENABLED", raising=False)
        with patch(
            "radbot.config.config_loader.config_loader.get_agent_config",
            return_value={"terse_protocol_enabled": True},
        ):
            assert is_terse_protocol_enabled() is True

    def test_defaults_false_when_neither_set(self, monkeypatch):
        monkeypatch.delenv("RADBOT_TERSE_PROTOCOL_ENABLED", raising=False)
        with patch(
            "radbot.config.config_loader.config_loader.get_agent_config",
            return_value={},
        ):
            assert is_terse_protocol_enabled() is False
