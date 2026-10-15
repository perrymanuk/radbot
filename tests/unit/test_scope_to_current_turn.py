"""Regression tests for the sub-agent scope-to-turn callback.

ADK presents other agents' events (beto's ``transfer_to_agent`` call and its
tool result) as ``role='user'`` text prefixed with "For context:". The trim
anchor must be the real user message, not one of those re-presented events.
"""

from types import SimpleNamespace

from google.adk.events import Event, EventActions
from google.adk.flows.llm_flows.contents import _get_contents
from google.genai import types

from radbot.callbacks.scope_to_current_turn import (
    _is_user_text,
    scope_sub_agent_context_callback,
)


def _user(text: str) -> types.Content:
    return types.Content(role="user", parts=[types.Part(text=text)])


def _model(text: str) -> types.Content:
    return types.Content(role="model", parts=[types.Part(text=text)])


def _texts(content: types.Content) -> list:
    return [p.text for p in content.parts if p.text]


def test_is_user_text_rejects_foreign_context_presentation():
    foreign = _user("For context:")
    foreign.parts.append(types.Part(text="[beto] called tool `transfer_to_agent`"))
    assert _is_user_text(_user("turn off the light")) is True
    assert _is_user_text(foreign) is False
    assert _is_user_text(_model("hi")) is False


def test_scope_keeps_user_request_after_transfer():
    # Arrange: build the history exactly as ADK's content builder presents it
    # to casa after beto transfers.
    events = [
        Event(invocation_id="i0", author="user", content=_user("what's the weather")),
        Event(invocation_id="i0", author="beto", content=_model("Sunny, dude.")),
        Event(invocation_id="i1", author="user", content=_user("turn off the light")),
        Event(
            invocation_id="i1",
            author="beto",
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        function_call=types.FunctionCall(
                            id="fc1",
                            name="transfer_to_agent",
                            args={"agent_name": "casa"},
                        )
                    )
                ],
            ),
        ),
        Event(
            invocation_id="i1",
            author="beto",
            actions=EventActions(transfer_to_agent="casa"),
            content=types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            id="fc1",
                            name="transfer_to_agent",
                            response={"result": None},
                        )
                    )
                ],
            ),
        ),
    ]
    req = SimpleNamespace(contents=_get_contents(None, events, "casa"))
    assert len(req.contents) == 5

    # Act
    scope_sub_agent_context_callback(None, req)

    # Assert: prior turn dropped, current user request + transfer context kept
    assert _texts(req.contents[0]) == ["turn off the light"]
    assert len(req.contents) == 3
    assert all("transfer_to_agent" in "".join(_texts(c)) for c in req.contents[1:])


def test_scope_noop_when_single_turn():
    req = SimpleNamespace(contents=[_user("hello")])
    scope_sub_agent_context_callback(None, req)
    assert _texts(req.contents[0]) == ["hello"]
