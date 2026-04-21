"""Unit tests for the schema-extraction library.

Follows the google-adk-python test idiom: construct real `FunctionTool` /
`LlmAgent` instances from plain Python callables, use `MagicMock(spec=...)`
only for ADK contexts we don't need to exercise, and assert on concrete
behavior (the produced `TypeAdapter`) rather than mocking the tool itself.
"""

from __future__ import annotations

from typing import Annotated

import pytest
from google.adk.agents.llm_agent import LlmAgent
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.function_tool import FunctionTool
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from tests.schema.extract import (
    MCPToolSkipped,
    SkippedTool,
    extract_pydantic_adapter,
    iter_tool_adapters,
)


def plain_add(a: int, b: int) -> int:
    """Add two ints."""
    return a + b


def constrained_search(
    query: str, year: Annotated[int, Field(ge=1900, le=2100)] = 2026
) -> str:
    """Search with a Python-level constraint that a Gemini proto would lose."""
    return f"{query}:{year}"


def with_context(
    query: str, tool_context
) -> str:  # noqa: ARG001 — mirrors ADK's injected param
    """Tool that declares the ADK-injected context param (must be filtered out)."""
    return query


class _FakeMCPTool:
    """Stand-in for google.adk.tools.mcp_tool.mcp_tool.MCPTool.

    The extractor detects MCP tools by module-name duck-typing; we mimic that by
    forcing `__module__` into the `mcp_tool` namespace.
    """

    __module__ = "google.adk.tools.mcp_tool.mcp_tool"
    name = "remote_mcp_thing"


class SearchInput(BaseModel):
    topic: str
    limit: int = Field(ge=1, le=50, default=10)


class test_function_tool:  # noqa: N801 — pytest class-less style not used; flat funcs below
    pass


def test_extracts_plain_function_tool_schema():
    tool = FunctionTool(plain_add)

    adapter = extract_pydantic_adapter(tool)

    # Valid payload passes.
    assert adapter.validate_python({"a": 1, "b": 2}) is not None
    # Missing required field fails.
    with pytest.raises(ValidationError):
        adapter.validate_python({"a": 1})


def test_extractor_enforces_pydantic_constraints_that_gemini_proto_would_drop():
    """The EX17 'pydantic-constraint drift' failure mode — this is the whole point."""
    tool = FunctionTool(constrained_search)

    adapter = extract_pydantic_adapter(tool)

    # In-bounds year passes.
    adapter.validate_python({"query": "hi", "year": 2026})
    # Out-of-bounds year that a lossy Gemini proto round-trip would accept as a plain int.
    with pytest.raises(ValidationError):
        adapter.validate_python({"query": "hi", "year": 1800})


def test_extractor_filters_adk_context_params():
    tool = FunctionTool(with_context)

    adapter = extract_pydantic_adapter(tool)

    # tool_context must not appear in the validated schema.
    validated = adapter.validate_python({"query": "ok"})
    assert "tool_context" not in validated.model_dump()


def test_agent_tool_uses_input_schema_when_present():
    agent = LlmAgent(
        name="searcher", model="gemini-2.5-flash", input_schema=SearchInput
    )
    tool = AgentTool(agent=agent)

    adapter = extract_pydantic_adapter(tool)

    adapter.validate_python({"topic": "llms", "limit": 5})
    with pytest.raises(ValidationError):
        adapter.validate_python({"topic": "llms", "limit": 999})


def test_agent_tool_defaults_to_request_string_when_no_input_schema():
    agent = LlmAgent(name="chatter", model="gemini-2.5-flash")
    tool = AgentTool(agent=agent)

    adapter = extract_pydantic_adapter(tool)

    adapter.validate_python({"request": "hello"})
    with pytest.raises(ValidationError):
        adapter.validate_python({})  # 'request' is required


def test_mcp_tool_raises_skip_marker():
    tool = _FakeMCPTool()

    with pytest.raises(MCPToolSkipped) as exc:
        extract_pydantic_adapter(tool)

    assert "mcp" in str(exc.value).lower() or "remote" in str(exc.value).lower()


def test_mcp_skip_is_notimplementederror_subclass():
    """Callers that catch NotImplementedError (the PT46 contract) must also catch the marker."""
    assert issubclass(MCPToolSkipped, NotImplementedError)


def test_iter_tool_adapters_records_skipped_mcp_tools():
    tools = [FunctionTool(plain_add), _FakeMCPTool()]

    results = dict(iter_tool_adapters(tools))

    assert isinstance(results["plain_add"], TypeAdapter)
    assert isinstance(results["remote_mcp_thing"], SkippedTool)
    assert results["remote_mcp_thing"].reason  # non-empty


def test_unknown_tool_shape_raises_not_implemented():
    class NotATool:
        pass

    with pytest.raises(NotImplementedError):
        extract_pydantic_adapter(NotATool())
