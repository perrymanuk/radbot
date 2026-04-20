"""Unit tests for the divergent ideation tool.

The LLM client is fully mocked — we never touch a real API here. A separate
integration test at ``tests/integration/test_divergent_ideation_live.py``
covers the real-API path and is skipped by default.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from radbot.tools.divergent_ideation import divergent_ideation as di_mod
from radbot.tools.divergent_ideation import execute_divergent_ideation


def _fake_client(stream_responses):
    """Build a fake genai.Client whose aio.models.generate_content honors a
    per-call side_effect list."""
    aio_models = MagicMock()
    aio_models.generate_content = AsyncMock(side_effect=stream_responses)
    return SimpleNamespace(aio=SimpleNamespace(models=aio_models))


def _response(text: str):
    return SimpleNamespace(text=text, usage_metadata=SimpleNamespace(total_token_count=42))


class TestExecuteDivergentIdeation:
    def test_all_streams_succeed(self):
        responses = [
            _response("Standard approach"),
            _response("Contrarian approach"),
            _response("Wildcard approach"),
        ]
        fake = _fake_client(responses)
        with patch.object(di_mod, "create_client_with_config_settings", return_value=fake):
            result = execute_divergent_ideation("how to scale a websocket server")

        assert result["status"] == "success"
        assert result["problem_statement"] == "how to scale a websocket server"
        assert result["standard"] == "Standard approach"
        assert result["contrarian"] == "Contrarian approach"
        assert result["wildcard"] == "Wildcard approach"
        assert "model" in result
        assert fake.aio.models.generate_content.await_count == 3

    def test_partial_failure_does_not_sink_batch(self):
        responses = [
            _response("Standard approach"),
            RuntimeError("boom — rate limited"),
            _response("Wildcard approach"),
        ]
        fake = _fake_client(responses)
        with patch.object(di_mod, "create_client_with_config_settings", return_value=fake):
            result = execute_divergent_ideation("design a sharded counter")

        assert result["status"] == "success"  # at least one stream succeeded
        assert result["standard"] == "Standard approach"
        assert isinstance(result["contrarian"], dict)
        assert result["contrarian"]["error"] == "RuntimeError"
        assert "boom" in result["contrarian"]["message"]
        assert result["wildcard"] == "Wildcard approach"

    def test_all_streams_fail_returns_error_status(self):
        responses = [
            RuntimeError("fail 1"),
            RuntimeError("fail 2"),
            RuntimeError("fail 3"),
        ]
        fake = _fake_client(responses)
        with patch.object(di_mod, "create_client_with_config_settings", return_value=fake):
            result = execute_divergent_ideation("anything")

        assert result["status"] == "error"
        assert "All ideation streams failed" in result["message"]
        for stream in ("standard", "contrarian", "wildcard"):
            assert isinstance(result[stream], dict)
            assert result[stream]["error"] == "RuntimeError"

    def test_empty_problem_statement(self):
        # Should short-circuit without building a client or calling the LLM.
        with patch.object(di_mod, "create_client_with_config_settings") as mk:
            result = execute_divergent_ideation("   ")
        assert result["status"] == "error"
        assert "non-empty" in result["message"]
        mk.assert_not_called()

    def test_client_construction_failure_is_reported(self):
        with patch.object(
            di_mod,
            "create_client_with_config_settings",
            side_effect=RuntimeError("no api key"),
        ):
            result = execute_divergent_ideation("x")
        assert result["status"] == "error"
        assert "no api key" in result["message"]

    def test_streams_run_in_parallel(self):
        """gather() should dispatch all three streams before any awaits
        resolve — verify via ordered start/finish tracking."""
        import asyncio

        events = []

        async def fake_generate(*, model, contents):
            events.append(("start", contents[:20]))
            await asyncio.sleep(0.01)
            events.append(("end", contents[:20]))
            return _response("ok")

        aio_models = MagicMock()
        aio_models.generate_content = AsyncMock(side_effect=fake_generate)
        fake = SimpleNamespace(aio=SimpleNamespace(models=aio_models))

        with patch.object(di_mod, "create_client_with_config_settings", return_value=fake):
            result = execute_divergent_ideation("design a cache")

        assert result["status"] == "success"
        # All three streams start before any finishes → first three events are "start".
        start_count_before_first_end = 0
        for kind, _ in events:
            if kind == "end":
                break
            start_count_before_first_end += 1
        assert start_count_before_first_end == 3

    def test_tool_is_registered_as_function_tool(self):
        from google.adk.tools import FunctionTool

        from radbot.tools.divergent_ideation import execute_divergent_ideation_tool

        assert isinstance(execute_divergent_ideation_tool, FunctionTool)
