"""Unit tests for SessionRunner._run_with_empty_content_retry.

Covers the selective retry on intermittent Gemini ``Content(parts=None)``:
- continuation path when the failed attempt did real (non-transfer) tool work
- reset path when there was no useful tool activity
- transfer-only activity classifies as no-tool-activity (reset)
- multi-attempt: tool work, then empty-no-tools, then text -> resets between

Bypasses ``__init__`` via ``object.__new__`` and assigns the minimum required
attributes — the helper only touches ``self.runner``, ``self.session_service``,
``self.user_id``, ``self.session_id``.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from google.genai.types import Content, Part

from radbot.web.api.session.session_runner import SessionRunner


def _make_runner_stub():
    """Build a SessionRunner with attributes wired but __init__ bypassed."""
    sr = object.__new__(SessionRunner)
    sr.user_id = "test-user"
    sr.session_id = "11111111-2222-3333-4444-555555555555"
    sr.agent_name = "beto"
    sr.runner = SimpleNamespace(app_name="beto")
    sr.session_service = SimpleNamespace(
        delete_session=AsyncMock(),
        create_session=AsyncMock(),
    )
    return sr


def _session(session_id: str = "11111111-2222-3333-4444-555555555555"):
    return SimpleNamespace(id=session_id, events=[])


def _text_event(text: str):
    return SimpleNamespace(content=SimpleNamespace(parts=[SimpleNamespace(text=text)]))


def _tool_response_event(name: str):
    """Event whose content carries a function_response with the given name."""
    return SimpleNamespace(
        content=SimpleNamespace(
            parts=[
                SimpleNamespace(
                    function_response=SimpleNamespace(name=name),
                    text=None,
                )
            ]
        )
    )


def _make_run_async(scripted_attempts):
    """Return a fake runner.run_async that yields scripted events per attempt.

    ``scripted_attempts`` is a list of lists of events; attempt N yields
    ``scripted_attempts[N]``.
    """
    state = {"attempt": 0}

    async def run_async(*args, **kwargs):
        i = state["attempt"]
        state["attempt"] += 1
        for ev in scripted_attempts[i]:
            yield ev

    return run_async, state


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Skip the inter-attempt backoff in tests."""

    async def _fast_sleep(_):
        return None

    monkeypatch.setattr(
        "radbot.web.api.session.session_runner.asyncio.sleep", _fast_sleep
    )


class TestContinuationPath:
    @pytest.mark.asyncio
    async def test_tool_work_then_text_uses_continuation_no_reset(self):
        sr = _make_runner_stub()
        attempts = [
            [
                _tool_response_event("search_youtube_videos")
            ],  # attempt 1: tool work, no text
            [_text_event("here are 10 crafting videos")],  # attempt 2: text
        ]
        run_async, state = _make_run_async(attempts)
        sr.runner.run_async = run_async

        session = _session()
        user_msg = Content(
            parts=[Part(text="find crafting videos for paula")], role="user"
        )

        new_session, events = await sr._run_with_empty_content_retry(
            session, user_msg, None
        )

        assert state["attempt"] == 2, "should stop after second attempt produced text"
        sr.session_service.delete_session.assert_not_called()
        sr.session_service.create_session.assert_not_called()
        assert (
            new_session is session
        ), "same-session continuation must keep session intact"
        assert len(events) == 2, "events from both attempts must be accumulated"


class TestResetPath:
    @pytest.mark.asyncio
    async def test_no_events_resets_session_and_replays_original(self):
        sr = _make_runner_stub()
        # Each reset returns a fresh session-like object
        sr.session_service.create_session = AsyncMock(
            side_effect=[_session(), _session()]
        )
        attempts = [[], [], [_text_event("ok")]]  # 3 attempts; only last has text
        run_async, _state = _make_run_async(attempts)
        sr.runner.run_async = run_async

        session = _session()
        user_msg = Content(parts=[Part(text="original request")], role="user")

        new_session, events = await sr._run_with_empty_content_retry(
            session, user_msg, None
        )

        # Reset fired on attempt 1 and attempt 2 (both had no events, no tool activity).
        assert sr.session_service.delete_session.await_count == 2
        assert sr.session_service.create_session.await_count == 2
        # Final attempt produced text
        assert len(events) == 1


class TestTransferOnlyClassifiesAsReset:
    @pytest.mark.asyncio
    async def test_transfer_to_agent_only_takes_reset_branch(self):
        sr = _make_runner_stub()
        sr.session_service.create_session = AsyncMock(
            side_effect=[_session(), _session()]
        )
        attempts = [
            [
                _tool_response_event("transfer_to_agent")
            ],  # only a transfer; not "tool work"
            [_text_event("here you go")],
        ]
        run_async, _state = _make_run_async(attempts)
        sr.runner.run_async = run_async

        session = _session()
        user_msg = Content(parts=[Part(text="do a thing")], role="user")

        new_session, events = await sr._run_with_empty_content_retry(
            session, user_msg, None
        )

        # Reset must fire — transfer-only is not substantive tool activity.
        assert sr.session_service.delete_session.await_count == 1
        assert sr.session_service.create_session.await_count == 1
        # Only attempt-2 events accumulate (attempt-1 was discarded with the session).
        assert len(events) == 1


class TestContinuationFailsThenReset:
    @pytest.mark.asyncio
    async def test_tool_work_then_empty_no_tools_then_text(self):
        sr = _make_runner_stub()
        sr.session_service.create_session = AsyncMock(side_effect=[_session()])
        attempts = [
            [
                _tool_response_event("search_youtube_videos")
            ],  # 1: tool work, no text -> continuation
            [],  # 2: empty, no tool work -> reset (accumulator wiped)
            [_text_event("answer")],  # 3: text
        ]
        run_async, _state = _make_run_async(attempts)
        sr.runner.run_async = run_async

        session = _session()
        user_msg = Content(parts=[Part(text="orig")], role="user")

        new_session, events = await sr._run_with_empty_content_retry(
            session, user_msg, None
        )

        # Continuation path on attempt 1: no reset.
        # Reset path on attempt 2: one delete, one create.
        assert sr.session_service.delete_session.await_count == 1
        assert sr.session_service.create_session.await_count == 1
        # accumulated_events was cleared by reset, then attempt-3 text was added.
        assert len(events) == 1
        assert events[0].content.parts[0].text == "answer"
