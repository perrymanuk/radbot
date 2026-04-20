"""Unit tests for `radbot.tools.divergent_ideation`.

All LLM calls are fully mocked — the suite never hits a real model.
Covers:
  * happy path: all three personas return text
  * partial failure: one persona times out; the other two still return,
    the failed slot contains an ``Error: ...`` string, and the tool does
    NOT raise.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from radbot.tools import divergent_ideation as di_module
from radbot.tools.divergent_ideation.tool import divergent_ideation


def _fake_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(text=text)


@pytest.mark.asyncio
async def test_happy_path_returns_three_paths():
    """All three personas succeed → dict with three populated paths, no errors."""

    captured_prompts: list[str] = []

    async def fake_generate_content(*, model, contents, config):  # noqa: ARG001
        captured_prompts.append(contents)
        # Match on unique persona-self-identification token; persona prompts
        # cross-reference each other, so a substring match on the persona
        # name alone would route to the wrong branch.
        if "You are the Pragmatic" in contents:
            return _fake_response("pragmatic prose")
        if "You are the Contrarian" in contents:
            return _fake_response("contrarian prose")
        if "You are the Wildcard" in contents:
            return _fake_response("wildcard prose")
        return _fake_response("unknown")

    fake_client = SimpleNamespace(
        aio=SimpleNamespace(
            models=SimpleNamespace(generate_content=fake_generate_content)
        )
    )

    with patch.object(
        di_module.tool, "create_client_with_config_settings", return_value=fake_client
    ), patch.object(di_module.tool, "_model", return_value="gemini-test"), patch.object(
        di_module.tool,
        "sanitize_external_content",
        side_effect=lambda text, **_: text,
    ):
        result = await divergent_ideation("How do we cool a 10kW rack quietly?")

    assert set(result.keys()) == {
        "pragmatic_path",
        "contrarian_path",
        "wildcard_path",
        "errors",
    }
    assert result["pragmatic_path"] == "pragmatic prose"
    assert result["contrarian_path"] == "contrarian prose"
    assert result["wildcard_path"] == "wildcard prose"
    assert result["errors"] == []
    # Three calls were made (one per persona) — proves parallel fan-out.
    assert len(captured_prompts) == 3


@pytest.mark.asyncio
async def test_partial_failure_one_persona_times_out():
    """Wildcard times out → the other two still return, wildcard slot is an error."""

    async def fake_generate_content(*, model, contents, config):  # noqa: ARG001
        if "You are the Wildcard" in contents:
            # Sleep longer than the per-call timeout so wait_for fires.
            await asyncio.sleep(5)
            return _fake_response("never returned")
        if "You are the Pragmatic" in contents:
            return _fake_response("pragmatic prose")
        if "You are the Contrarian" in contents:
            return _fake_response("contrarian prose")
        return _fake_response("unknown")

    fake_client = SimpleNamespace(
        aio=SimpleNamespace(
            models=SimpleNamespace(generate_content=fake_generate_content)
        )
    )

    # Shrink the timeout so the test runs fast.
    with patch.object(
        di_module.tool, "create_client_with_config_settings", return_value=fake_client
    ), patch.object(di_module.tool, "_model", return_value="gemini-test"), patch.object(
        di_module.tool,
        "sanitize_external_content",
        side_effect=lambda text, **_: text,
    ), patch.object(di_module.tool, "PER_CALL_TIMEOUT_SECONDS", 0.05):
        result = await divergent_ideation("Design a self-healing deploy.")

    # Tool did NOT raise — partial result returned.
    assert result["pragmatic_path"] == "pragmatic prose"
    assert result["contrarian_path"] == "contrarian prose"
    assert result["wildcard_path"].startswith("Error:")
    assert "Timeout" in result["wildcard_path"]
    assert result["errors"] == ["wildcard"]


@pytest.mark.asyncio
async def test_partial_failure_one_persona_raises_exception():
    """Contrarian raises → other two still return, contrarian slot has error string."""

    async def fake_generate_content(*, model, contents, config):  # noqa: ARG001
        if "You are the Contrarian" in contents:
            raise RuntimeError("rate limit exceeded")
        if "You are the Pragmatic" in contents:
            return _fake_response("pragmatic prose")
        if "You are the Wildcard" in contents:
            return _fake_response("wildcard prose")
        return _fake_response("unknown")

    fake_client = SimpleNamespace(
        aio=SimpleNamespace(
            models=SimpleNamespace(generate_content=fake_generate_content)
        )
    )

    with patch.object(
        di_module.tool, "create_client_with_config_settings", return_value=fake_client
    ), patch.object(di_module.tool, "_model", return_value="gemini-test"), patch.object(
        di_module.tool,
        "sanitize_external_content",
        side_effect=lambda text, **_: text,
    ):
        result = await divergent_ideation("Pick a vector DB.")

    assert result["pragmatic_path"] == "pragmatic prose"
    assert result["wildcard_path"] == "wildcard prose"
    assert result["contrarian_path"].startswith("Error:")
    assert "rate limit exceeded" in result["contrarian_path"]
    assert result["errors"] == ["contrarian"]


@pytest.mark.asyncio
async def test_empty_problem_statement_returns_errors_without_calling_llm():
    """Guard clause — empty input never hits the model."""

    called = False

    def boom(*_a, **_kw):
        nonlocal called
        called = True
        raise AssertionError("LLM client must not be constructed for empty input")

    with patch.object(di_module.tool, "create_client_with_config_settings", side_effect=boom):
        result = await divergent_ideation("   ")

    assert called is False
    assert result["errors"] == ["pragmatic", "contrarian", "wildcard"]
    assert result["pragmatic_path"].startswith("Error:")
