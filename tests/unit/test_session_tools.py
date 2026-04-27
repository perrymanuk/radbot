"""Unit tests for the Claude Code session tools (EX35/PT96).

Covers the strict Pydantic boundary that forces every kickoff through a Telos
``task_ref`` (``^(PT|EX)\\d+$``). The validator must reject raw prompts and
keep the agent loop alive by surfacing errors as ``{status: "error"}`` dicts
rather than uncaught exceptions.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from radbot.tools.claude_code_session import session_tools
from radbot.tools.claude_code_session.session_tools import (
    ClaudeSessionRequest,
    _synthesize_prompt,
    run_claude_session,
    start_claude_session,
)

# ---------------------------------------------------------------------------
# Schema validator
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ref", ["PT1", "PT96", "EX35", "PT9999"])
def test_task_ref_accepts_valid_telos_codes(ref: str) -> None:
    req = ClaudeSessionRequest(task_ref=ref, target_dir="/tmp")
    assert req.task_ref == ref


@pytest.mark.parametrize(
    "ref",
    [
        "",
        "pt96",  # lowercase rejected — Telos refs are uppercase
        "PT",
        "PT-96",
        "PT 96",
        "PT96 ",
        " PT96",
        "MS3",  # milestones aren't an executable handle
        "G1",
        "execute PT96",
        "ls -la",
        "rm -rf /",
        "write a script that does X",
        "print('hello')",
        "PT96; rm -rf /",
        "PT96\nrm -rf /",
    ],
)
def test_task_ref_rejects_anything_other_than_pt_or_ex(ref: str) -> None:
    with pytest.raises(ValidationError):
        ClaudeSessionRequest(task_ref=ref, target_dir="/tmp")


def test_validation_error_message_guides_scout_back_to_telos() -> None:
    with pytest.raises(ValidationError) as exc:
        ClaudeSessionRequest(task_ref="write a script", target_dir="/tmp")
    msg = str(exc.value)
    assert "task_ref" in msg
    assert "(PT|EX)" in msg


# ---------------------------------------------------------------------------
# Prompt synthesis
# ---------------------------------------------------------------------------


def test_synthesize_prompt_with_auto_ship() -> None:
    assert (
        _synthesize_prompt("PT96", auto_ship=True)
        == "execute PT96 and use /ship when complete"
    )


def test_synthesize_prompt_without_auto_ship() -> None:
    assert _synthesize_prompt("EX35", auto_ship=False) == "execute EX35"


# ---------------------------------------------------------------------------
# start_claude_session: error interception
# ---------------------------------------------------------------------------


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


@pytest.mark.parametrize(
    "bogus",
    ["write a script that pings prod", "ls -la", "PT 96", "", "pt96"],
)
def test_start_claude_session_returns_error_dict_for_invalid_ref(bogus: str) -> None:
    """Validation errors must be caught and returned, not raised."""
    with patch.object(session_tools, "ClaudeCodeClient") as client_cls:
        result = _run(start_claude_session(task_ref=bogus, target_dir="/tmp"))
    assert result["status"] == "error"
    assert "task_ref" in result["message"]
    # Client must not be touched when validation fails.
    client_cls.assert_not_called()


def test_run_claude_session_returns_error_dict_for_invalid_ref() -> None:
    with patch.object(session_tools, "ClaudeCodeClient") as client_cls:
        result = _run(run_claude_session(task_ref="rm -rf /", target_dir="/tmp"))
    assert result["status"] == "error"
    assert "task_ref" in result["message"]
    client_cls.assert_not_called()


# ---------------------------------------------------------------------------
# Happy path: valid task_ref drives synthesis through to the client
# ---------------------------------------------------------------------------


def _fake_session(job_id: str = "job-1") -> MagicMock:
    s = MagicMock()
    s.job_id = job_id
    s.status = "running"
    s.waiting_for_input = False
    s.pending_question = None
    s.session_id = None
    s.return_code = None
    s.stderr_chunks = []
    s.output = []
    return s


def test_start_claude_session_synthesizes_prompt_from_task_ref() -> None:
    fake = _fake_session()
    fake_client = MagicMock()
    fake_client.start_background_session = AsyncMock(return_value=fake)

    with patch.object(session_tools, "ClaudeCodeClient", return_value=fake_client):
        result = _run(
            start_claude_session(task_ref="PT96", target_dir="/work", auto_ship=True)
        )

    assert result["status"] == "success"
    assert result["job_id"] == "job-1"

    fake_client.start_background_session.assert_awaited_once()
    kwargs = fake_client.start_background_session.await_args.kwargs
    assert kwargs["working_dir"] == "/work"
    assert kwargs["prompt"] == "execute PT96 and use /ship when complete"


def test_start_claude_session_omits_ship_when_auto_ship_false() -> None:
    fake = _fake_session()
    fake_client = MagicMock()
    fake_client.start_background_session = AsyncMock(return_value=fake)

    with patch.object(session_tools, "ClaudeCodeClient", return_value=fake_client):
        _run(start_claude_session(task_ref="EX35", target_dir="/work", auto_ship=False))

    kwargs = fake_client.start_background_session.await_args.kwargs
    assert kwargs["prompt"] == "execute EX35"


# ---------------------------------------------------------------------------
# Surface guarantee: the public functions never accept a `prompt` kwarg
# ---------------------------------------------------------------------------


def test_start_claude_session_does_not_accept_prompt_kwarg() -> None:
    import inspect

    params = inspect.signature(start_claude_session).parameters
    assert "prompt" not in params
    assert "task_ref" in params


def test_run_claude_session_does_not_accept_custom_prompt_kwarg() -> None:
    import inspect

    params = inspect.signature(run_claude_session).parameters
    assert "custom_prompt" not in params
    assert "prompt" not in params
    assert "task_ref" in params
