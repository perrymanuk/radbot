"""
Research agent factory.

This module provides factory functions for creating research agents.
"""

import logging
from typing import Any, List, Optional, Union

# Import project components
from radbot.agent.research_agent.agent import ResearchAgent
from radbot.agent.shared import TASK_FINISH_INSTRUCTIONS, TRANSFER_INSTRUCTIONS
from radbot.config import config_manager

# Import ADK components


logger = logging.getLogger(__name__)


def _build_scout_toolkit() -> List[Any]:
    """Assemble scout's full research + planning toolkit.

    Used in both session modes (sub-agent under beto, root of a scout session),
    so scout behaves consistently whichever way she's reached.
    """
    toolkit: List[Any] = []

    # Agent-scoped memory
    try:
        from radbot.tools.memory.agent_memory_factory import create_agent_memory_tools

        toolkit.extend(create_agent_memory_tools("scout"))
    except Exception as e:  # memory is important but should not block startup
        logger.warning("Scout: memory tools unavailable: %s", e)

    # Wiki read-only
    try:
        from radbot.tools.wiki import WIKI_TOOLS

        toolkit.extend(WIKI_TOOLS)
    except Exception as e:
        logger.warning("Scout: wiki tools unavailable: %s", e)

    # Guardrailed web fetch
    try:
        from radbot.tools.web_research import WEB_RESEARCH_TOOLS

        toolkit.extend(WEB_RESEARCH_TOOLS)
    except Exception as e:
        logger.warning("Scout: web_research tools unavailable: %s", e)

    # Telos subset — read + plan writes (add_exploration, add_task, add_milestone,
    # add_journal). No identity / goal mutation, no project meta-management.
    try:
        from radbot.tools.telos import SCOUT_TELOS_TOOLS

        toolkit.extend(SCOUT_TELOS_TOOLS)
    except Exception as e:
        logger.warning("Scout: Telos subset unavailable: %s", e)

    # Plan Council — 3 core critics + 1 on-demand UX/DX + the trigger heuristic.
    # Scout orchestrates the rounds herself; no hidden aggregator.
    try:
        from radbot.tools.council import COUNCIL_TOOLS, should_convene_council_tool

        toolkit.extend(COUNCIL_TOOLS)
        toolkit.append(should_convene_council_tool)
    except Exception as e:
        logger.warning("Scout: plan council unavailable: %s", e)

    # Read-only code exploration (EX9). Lets scout sync public repos into
    # /data/repos and search them with rg, so she can produce file manifests
    # for Claude Code without running an LSP. PT35 adds repo_map +
    # repo_references on top of the same module.
    try:
        from radbot.tools.repo_exploration import REPO_EXPLORATION_TOOLS

        toolkit.extend(REPO_EXPLORATION_TOOLS)
    except Exception as e:
        logger.warning("Scout: repo_exploration tools unavailable: %s", e)

    # Divergent ideation — three parallel persona calls (Pragmatic, Contrarian,
    # Wildcard) with graceful degradation. See `explorations: EX5` in Telos.
    try:
        from radbot.tools.divergent_ideation import divergent_ideation_tool

        toolkit.append(divergent_ideation_tool)
    except Exception as e:
        logger.warning("Scout: divergent_ideation unavailable: %s", e)

    return toolkit


def create_research_agent(
    name: str = "scout",
    model: Optional[str] = None,
    custom_instruction: Optional[str] = None,
    tools: Optional[List[Any]] = None,
    as_subagent: bool = True,
    as_root: bool = False,
    sub_agents: Optional[List[Any]] = None,
    enable_google_search: bool = False,
    enable_code_execution: bool = False,
    app_name: Optional[str] = None,
) -> Union[ResearchAgent, Any]:
    """
    Create a research agent with the specified configuration.

    Args:
        name: Name of the agent (should be "scout" for consistent transfers)
        model: LLM model to use (defaults to config setting)
        custom_instruction: Optional custom instruction to override the default
        tools: List of tools to provide to the agent
        as_subagent: Whether to return the ResearchAgent or the underlying ADK agent
        enable_google_search: Whether to enable Google Search capability
        enable_code_execution: Whether to enable Code Execution capability
        app_name: Application name (should match the parent agent name for ADK 0.4.0+)

    Returns:
        Union[ResearchAgent, Any]: The created agent instance
    """
    # Ensure agent name is always "scout" for consistent transfers
    if name != "scout":
        logger.warning(
            f"Agent name '{name}' changed to 'scout' for consistent transfers"
        )
        name = "scout"

    # Use agent-specific model or fall back to default
    if model is None:
        model = config_manager.get_agent_model("scout_agent")
        logger.info(f"Using model from config for scout_agent: {model}")

    # app_name rules (ADK 2.0 requires match with root agent name):
    #  - as_root=True  → "scout" (scout IS the root of her own session)
    #  - as_root=False → "beto"  (scout is beto's sub-agent, shares beto's session partition)
    if app_name is None:
        app_name = "scout" if as_root else "beto"

    # Resolve scout's instruction. Prefer `config/default_configs/instructions/scout.md`
    # (same pattern every other domain agent uses); fall back to the
    # Python-embedded prompt only when the file is missing.
    instruction = custom_instruction
    if instruction is None:
        try:
            instruction = config_manager.get_instruction("scout")
            logger.info("Scout: loaded instruction from scout.md")
        except FileNotFoundError:
            logger.warning(
                "Scout: scout.md not found, falling back to embedded instruction"
            )

    # Assemble scout's toolkit (same in both modes for behavioral consistency).
    # Caller-supplied `tools` are appended after the standard toolkit.
    toolkit = _build_scout_toolkit()
    if tools:
        toolkit.extend(tools)

    # Create the research agent with explicit name and app_name.
    # ADK 2.0 requires the Runner's root LlmAgent to be in "chat" mode — the
    # sub-agent default ``mode="task"`` triggers a startup error on the first
    # real turn. When scout is being constructed as a session root, swap to
    # "chat"; sub-agent usage keeps "task" so we don't disturb the existing
    # beto→scout transfer path.
    research_agent = ResearchAgent(
        name=name,
        model=model,
        instruction=instruction,  # None → ResearchAgent falls back to embedded default
        tools=toolkit,
        enable_sequential_thinking=True,
        enable_google_search=enable_google_search,
        enable_code_execution=enable_code_execution,
        app_name=app_name,  # Should match the root agent's name
        mode="chat" if as_root else "task",
    )

    adk_agent = research_agent.get_adk_agent()

    logger.info("Scout toolkit loaded (%d tools)", len(toolkit))

    # Note: transfer_to_agent is NOT added here explicitly — ADK auto-injects it
    # for any agent that is part of a sub_agents tree. Adding it explicitly causes
    # a "Duplicate function declaration" error from the Gemini API.

    # Append completion instructions (task or transfer depending on V1/V2 mode).
    # Root agents don't transfer — they ARE the root, the next agent on the
    # receiving end is the user, and ADK doesn't auto-inject
    # ``transfer_to_agent`` unless the agent has sub-agents. Appending
    # TRANSFER_INSTRUCTIONS on a root would tell the model to call a tool
    # that isn't registered → "Tool 'transfer_to_agent' not found" on the
    # first turn that tries to "return control." Skip entirely for as_root.
    if not as_root and hasattr(adk_agent, "instruction") and adk_agent.instruction:
        try:
            from google.adk.features import FeatureName, is_feature_enabled

            v2_active = not is_feature_enabled(FeatureName.V1_LLM_AGENT)
        except Exception:
            v2_active = False
        adk_agent.instruction += (
            TASK_FINISH_INSTRUCTIONS if v2_active else TRANSFER_INSTRUCTIONS
        )

    # Root-mode wiring: attach sub-agents (search_agent sits under scout for
    # grounded Google) and the persona/sanitize/telemetry callback stack that
    # beto uses — scout is responsible for her own session hygiene when she's
    # the root.
    if as_root:
        if sub_agents:
            adk_agent.sub_agents = list(sub_agents)

        try:
            from radbot.callbacks.empty_content_callback import (
                handle_empty_response_after_model,
                scrub_empty_content_before_model,
            )
            from radbot.callbacks.sanitize_callback import (
                sanitize_before_model_callback,
            )
            from radbot.callbacks.sanitize_tool_schemas import (
                sanitize_tool_schemas_before_model,
            )
            from radbot.callbacks.telemetry_callback import (
                telemetry_after_model_callback,
            )
            from radbot.tools.telos import inject_telos_context

            adk_agent.before_model_callback = [
                scrub_empty_content_before_model,
                sanitize_before_model_callback,
                sanitize_tool_schemas_before_model,
                inject_telos_context,
            ]
            adk_agent.after_model_callback = [
                handle_empty_response_after_model,
                telemetry_after_model_callback,
            ]
            logger.info("Scout root callbacks attached (sanitize + telos + telemetry)")
        except Exception as e:
            logger.warning("Failed to attach root callbacks to Scout: %s", e)

        # Root-mode must return the bare ADK agent — the Runner expects a
        # ``BaseAgent``, not the ResearchAgent wrapper.
        return adk_agent

    # Sub-agent mode — preserve the existing return-type switch
    if as_subagent:
        return research_agent

    if hasattr(adk_agent, "name") and adk_agent.name != name:
        logger.warning(
            f"ADK Agent name mismatch: '{adk_agent.name}' not '{name}' - fixing"
        )
        adk_agent.name = name
    return adk_agent
