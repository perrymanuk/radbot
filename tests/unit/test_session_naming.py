"""Unit tests for the session auto-naming service (PT63 / PT67).

Mocks the two external boundaries — `chat_operations` (DB) and
`google.genai.Client` (LLM) — and exercises the pure-Python paths:
markdown fence stripping, timeout handling, empty-history short-circuit,
and fallback model resolution.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from radbot.services import session_naming

SESSION_ID = "11111111-2222-3333-4444-555555555555"


def _make_messages(n: int) -> list[dict]:
    return [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"}
        for i in range(n)
    ]


def _patch_llm(monkeypatch, text: str):
    """Replace the genai.Client call site with a canned response."""

    def fake_call(model, prompt, api_key):
        return text

    monkeypatch.setattr(session_naming, "_call_llm", fake_call)


def _patch_api_key(monkeypatch, key: str = "test-key"):
    monkeypatch.setattr(session_naming, "_get_api_key", lambda: key)


def _patch_model(monkeypatch, name: str = "stub-model"):
    monkeypatch.setattr(session_naming, "_resolve_naming_model", lambda: name)


class TestAutoNameSessionShortCircuit:
    def test_auto_name_session_short_circuits_on_empty_history(self, monkeypatch):
        monkeypatch.setattr(
            session_naming.chat_operations,
            "get_messages_by_session_id",
            lambda **_: [],
        )

        ok, msg = session_naming.auto_name_session(SESSION_ID)

        assert ok is False
        assert msg == "Not enough history to name session"

    def test_auto_name_session_short_circuits_on_single_message(self, monkeypatch):
        monkeypatch.setattr(
            session_naming.chat_operations,
            "get_messages_by_session_id",
            lambda **_: _make_messages(1),
        )

        ok, msg = session_naming.auto_name_session(SESSION_ID)

        assert ok is False
        assert msg == "Not enough history to name session"


class TestAutoNameSessionMarkdownStripping:
    @pytest.fixture
    def wired(self, monkeypatch):
        monkeypatch.setattr(
            session_naming.chat_operations,
            "get_messages_by_session_id",
            lambda **_: _make_messages(4),
        )
        persisted = MagicMock(return_value=True)
        monkeypatch.setattr(
            session_naming.chat_operations, "create_or_update_session", persisted
        )
        _patch_api_key(monkeypatch)
        _patch_model(monkeypatch)
        return persisted

    def test_auto_name_session_strips_json_markdown_fences(self, monkeypatch, wired):
        _patch_llm(monkeypatch, '```json\n{"name": "Weekend Plans"}\n```')

        ok, name = session_naming.auto_name_session(SESSION_ID)

        assert ok is True
        assert name == "Weekend Plans"
        wired.assert_called_once()
        assert wired.call_args.kwargs["name"] == "Weekend Plans"

    def test_auto_name_session_strips_plain_markdown_fences(self, monkeypatch, wired):
        _patch_llm(monkeypatch, '```\n{"name": "Dinner Ideas"}\n```')

        ok, name = session_naming.auto_name_session(SESSION_ID)

        assert ok is True
        assert name == "Dinner Ideas"

    def test_auto_name_session_accepts_raw_json(self, monkeypatch, wired):
        _patch_llm(monkeypatch, '{"name": "Radbot Deployment"}')

        ok, name = session_naming.auto_name_session(SESSION_ID)

        assert ok is True
        assert name == "Radbot Deployment"

    def test_auto_name_session_extracts_embedded_json_object(self, monkeypatch, wired):
        _patch_llm(monkeypatch, 'Sure! Here is the title: {"name": "Trip Prep"}.')

        ok, name = session_naming.auto_name_session(SESSION_ID)

        assert ok is True
        assert name == "Trip Prep"

    def test_auto_name_session_truncates_overlong_name(self, monkeypatch, wired):
        too_long = "A" * (session_naming.MAX_NAME_LENGTH + 50)
        _patch_llm(monkeypatch, '{"name": "' + too_long + '"}')

        ok, name = session_naming.auto_name_session(SESSION_ID)

        assert ok is True
        assert len(name) == session_naming.MAX_NAME_LENGTH

    def test_auto_name_session_rejects_unparseable_llm_output(self, monkeypatch, wired):
        _patch_llm(monkeypatch, "absolutely not json at all")

        ok, msg = session_naming.auto_name_session(SESSION_ID)

        assert ok is False
        assert msg == "Could not parse naming response"
        wired.assert_not_called()

    def test_auto_name_session_rejects_empty_name_field(self, monkeypatch, wired):
        _patch_llm(monkeypatch, '{"name": ""}')

        ok, msg = session_naming.auto_name_session(SESSION_ID)

        assert ok is False
        assert msg == "Could not parse naming response"


class TestAutoNameSessionTimeoutHandling:
    def test_auto_name_session_returns_timeout_when_llm_exceeds_budget(
        self, monkeypatch
    ):
        monkeypatch.setattr(
            session_naming.chat_operations,
            "get_messages_by_session_id",
            lambda **_: _make_messages(4),
        )
        monkeypatch.setattr(
            session_naming.chat_operations, "create_or_update_session", MagicMock()
        )
        _patch_api_key(monkeypatch)
        _patch_model(monkeypatch)
        monkeypatch.setattr(session_naming, "LLM_TIMEOUT_SECONDS", 0.05)

        import time

        def slow_llm(model, prompt, api_key):
            time.sleep(0.3)
            return '{"name": "Too Slow"}'

        monkeypatch.setattr(session_naming, "_call_llm", slow_llm)

        ok, msg = session_naming.auto_name_session(SESSION_ID)

        assert ok is False
        assert msg == "Naming timed out"

    def test_auto_name_session_returns_error_when_llm_raises(self, monkeypatch):
        monkeypatch.setattr(
            session_naming.chat_operations,
            "get_messages_by_session_id",
            lambda **_: _make_messages(4),
        )
        _patch_api_key(monkeypatch)
        _patch_model(monkeypatch)

        def boom(model, prompt, api_key):
            raise RuntimeError("API down")

        monkeypatch.setattr(session_naming, "_call_llm", boom)

        ok, msg = session_naming.auto_name_session(SESSION_ID)

        assert ok is False
        assert msg == "Naming model call failed"


class TestAutoNameSessionModelResolution:
    def test_resolve_naming_model_prefers_env_var(self, monkeypatch):
        monkeypatch.setenv("RADBOT_NAMING_MODEL", "gemini-env-override")

        assert session_naming._resolve_naming_model() == "gemini-env-override"

    def test_resolve_naming_model_falls_back_to_main_model_when_unset(
        self, monkeypatch
    ):
        monkeypatch.delenv("RADBOT_NAMING_MODEL", raising=False)

        fake_cfg = SimpleNamespace(
            model_config={"agent_models": {}},
            get_main_model=lambda: "gemini-main-fallback",
        )
        with patch.dict(
            "sys.modules",
            {
                "radbot.config": SimpleNamespace(config_manager=fake_cfg),
            },
        ):
            model = session_naming._resolve_naming_model()

        assert model == "gemini-main-fallback"

    def test_resolve_naming_model_picks_agent_models_naming_key(self, monkeypatch):
        monkeypatch.delenv("RADBOT_NAMING_MODEL", raising=False)

        fake_cfg = SimpleNamespace(
            model_config={"agent_models": {"naming_model": "gemini-cheap"}},
            get_main_model=lambda: "gemini-main",
        )
        with patch.dict(
            "sys.modules",
            {"radbot.config": SimpleNamespace(config_manager=fake_cfg)},
        ):
            model = session_naming._resolve_naming_model()

        assert model == "gemini-cheap"


class TestAutoNameSessionApiKey:
    def test_auto_name_session_fails_when_no_api_key_configured(self, monkeypatch):
        monkeypatch.setattr(
            session_naming.chat_operations,
            "get_messages_by_session_id",
            lambda **_: _make_messages(4),
        )
        monkeypatch.setattr(session_naming, "_get_api_key", lambda: None)

        ok, msg = session_naming.auto_name_session(SESSION_ID)

        assert ok is False
        assert msg == "No Google API key configured"


class TestAutoNameSessionPersistenceFailures:
    def test_auto_name_session_reports_save_failure(self, monkeypatch):
        monkeypatch.setattr(
            session_naming.chat_operations,
            "get_messages_by_session_id",
            lambda **_: _make_messages(4),
        )
        monkeypatch.setattr(
            session_naming.chat_operations,
            "create_or_update_session",
            lambda **_: False,
        )
        _patch_api_key(monkeypatch)
        _patch_model(monkeypatch)
        _patch_llm(monkeypatch, '{"name": "Saved Never"}')

        ok, msg = session_naming.auto_name_session(SESSION_ID)

        assert ok is False
        assert msg == "Could not save session name"

    def test_auto_name_session_handles_history_load_error(self, monkeypatch):
        def kaboom(**_):
            raise RuntimeError("DB is down")

        monkeypatch.setattr(
            session_naming.chat_operations, "get_messages_by_session_id", kaboom
        )

        ok, msg = session_naming.auto_name_session(SESSION_ID)

        assert ok is False
        assert msg == "Could not load session history"
