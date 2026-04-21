"""Shared schema-extraction library for RadBot tool validation.

Produces a `pydantic.TypeAdapter` for a tool's input payload so that both the
PR-gate static lint and the FakeLlm runtime validator can enforce that mock /
fixture payloads satisfy the real Python-level constraints of the callable —
constraints that are lossy when round-tripped through the Gemini schema proto
(EX17 "pydantic-constraint drift").

Public API:
    extract_pydantic_adapter(tool) -> TypeAdapter
    MCPToolSkipped                   (NotImplementedError subclass / skip marker)
    iter_tool_adapters(tools)        (lint helper that skips MCP tools)
"""

from __future__ import annotations

import inspect
import typing
from dataclasses import dataclass
from typing import Any, Callable, Iterator

from pydantic import BaseModel, TypeAdapter, create_model


class MCPToolSkipped(NotImplementedError):
    """Raised for MCP-proxied tools — schemas live on the remote server.

    Doubles as the skip marker: lint / validator call sites catch this and
    record a skip rather than failing. See EX17 rubric item 2.
    """


@dataclass(frozen=True)
class SkippedTool:
    """Record emitted by `iter_tool_adapters` for tools we can't introspect."""

    tool_name: str
    reason: str


_CONTEXT_PARAM_NAMES = frozenset({"tool_context", "callback_context", "input_stream"})


def _is_mcp_tool(tool: Any) -> bool:
    # Duck-typed to avoid importing the ADK MCP module at lint time (it pulls
    # in async MCP machinery). Fall back to the real class if available.
    cls = type(tool)
    mod = getattr(cls, "__module__", "") or ""
    if "mcp_tool" in mod or "mcp_toolset" in mod:
        return True
    return cls.__name__ in {"MCPTool", "McpTool"}


def _callable_to_model(func: Callable[..., Any], *, model_name: str) -> type[BaseModel]:
    """Build a pydantic model mirroring the callable's keyword signature.

    Skips ADK-injected context params and variadic *args/**kwargs. Parameters
    without annotations are typed as `Any` — this matches the permissiveness of
    `FunctionTool._get_declaration` while still letting pydantic enforce any
    annotations / `Annotated[..., Field(...)]` constraints that *are* present.
    """
    try:
        sig = inspect.signature(func)
    except (TypeError, ValueError) as exc:
        raise NotImplementedError(f"cannot inspect {func!r}: {exc}") from exc

    # Resolve string annotations (PEP 563 / `from __future__ import annotations`)
    # back to real types, preserving `Annotated[...]` metadata like Field(ge=...).
    try:
        resolved_hints = typing.get_type_hints(func, include_extras=True)
    except Exception:
        resolved_hints = {}

    fields: dict[str, tuple[Any, Any]] = {}
    for name, param in sig.parameters.items():
        if name in _CONTEXT_PARAM_NAMES:
            continue
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        if name in resolved_hints:
            annotation = resolved_hints[name]
        elif param.annotation is not inspect.Parameter.empty:
            annotation = param.annotation
        else:
            annotation = Any
        default = ... if param.default is inspect.Parameter.empty else param.default
        fields[name] = (annotation, default)

    model = create_model(model_name, **fields)  # type: ignore[call-overload]
    model.model_rebuild(force=True)
    return model


def _agent_input_model(tool: Any) -> type[BaseModel]:
    agent = getattr(tool, "agent", None)
    if agent is None:
        raise NotImplementedError(f"AgentTool {tool!r} has no .agent attribute")

    # LlmAgent exposes `input_schema`; composite agents may delegate to a sub.
    schema = getattr(agent, "input_schema", None)
    if schema is None and getattr(agent, "sub_agents", None):
        schema = getattr(agent.sub_agents[0], "input_schema", None)

    if schema is not None and inspect.isclass(schema) and issubclass(schema, BaseModel):
        return schema

    # ADK's default when no input_schema: {"request": str}.
    return create_model(f"{agent.name}Input", request=(str, ...))


def extract_pydantic_adapter(tool: Any) -> TypeAdapter:
    """Return a `TypeAdapter` that validates the tool's input payload.

    Raises:
        MCPToolSkipped: for MCP-proxied tools. Callers must catch and record a
            skip — MCP schemas are defined remotely and cannot be round-tripped
            through pydantic without contacting the server.
        NotImplementedError: for other un-introspectable tool shapes.
    """
    if _is_mcp_tool(tool):
        name = getattr(tool, "name", type(tool).__name__)
        raise MCPToolSkipped(f"{name} is MCP-proxied; schema is defined remotely")

    if hasattr(tool, "agent"):
        model = _agent_input_model(tool)
        return TypeAdapter(model)

    func = getattr(tool, "func", None)
    if callable(func):
        model_name = getattr(tool, "name", None) or func.__name__
        model = _callable_to_model(func, model_name=f"{model_name}Input")
        return TypeAdapter(model)

    if callable(tool):
        model_name = getattr(tool, "__name__", type(tool).__name__)
        model = _callable_to_model(tool, model_name=f"{model_name}Input")
        return TypeAdapter(model)

    raise NotImplementedError(
        f"don't know how to extract a schema from {type(tool).__name__} "
        f"(module {type(tool).__module__})"
    )


def iter_tool_adapters(
    tools: list[Any],
) -> Iterator[tuple[str, TypeAdapter | SkippedTool]]:
    """Yield `(name, adapter_or_skip)` pairs for a list of tools.

    MCP tools (and other un-introspectable tools) yield a `SkippedTool` record
    so the lint produces a stable manifest including what was skipped and why.
    """
    for tool in tools:
        name = (
            getattr(tool, "name", None)
            or getattr(tool, "__name__", None)
            or type(tool).__name__
        )
        try:
            yield name, extract_pydantic_adapter(tool)
        except MCPToolSkipped as exc:
            yield name, SkippedTool(tool_name=name, reason=str(exc))
        except NotImplementedError as exc:
            yield name, SkippedTool(tool_name=name, reason=f"unsupported: {exc}")
