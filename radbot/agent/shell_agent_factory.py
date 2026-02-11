"""
Factory functions for creating agents with shell command execution capabilities.

This module provides specialized factory functions for creating agents
with secure shell command execution.
"""

import logging
from typing import Any, Dict, List, Optional

from google.adk.agents import Agent

from radbot.agent.agent import AgentFactory, RadBotAgent, create_agent
from radbot.config.settings import ConfigManager
from radbot.tools.shell import get_shell_tool

logger = logging.getLogger(__name__)


def create_shell_agent(
    model: Optional[str] = None,
    base_tools: Optional[List[Any]] = None,
    instruction_name: str = "main_agent",
    config: Optional[ConfigManager] = None,
    strict_mode: bool = True,
    use_claude_cli: bool = False,
) -> RadBotAgent:
    """
    Create a RadBot agent with shell command execution capabilities.

    This factory function creates an agent with secure shell command execution,
    with optional strict or allow-all mode.

    Args:
        model: Optional model to use
        base_tools: Optional list of base tools to include
        instruction_name: Name of instruction to load from config
        config: Optional ConfigManager instance
        strict_mode: When True, only allow-listed commands are permitted.
                    When False, any command can be executed (SECURITY RISK).
        use_claude_cli: Whether to use Claude CLI for command execution (default: False)

    Returns:
        A RadBotAgent with shell command execution capabilities
    """
    # Start with base tools or empty list
    tools = list(base_tools or [])

    # Create the shell command tool (now returns ADK-compatible FunctionTool)
    shell_tool = get_shell_tool(strict_mode=strict_mode, use_claude_cli=use_claude_cli)

    # Log security mode and execution backend
    if use_claude_cli:
        backend_info = "using Claude CLI backend"
    else:
        backend_info = "using subprocess backend"

    if strict_mode:
        logger.info(
            f"Adding shell command execution tool in STRICT mode (only allow-listed commands) {backend_info}"
        )
    else:
        logger.warning(
            f"Adding shell command execution tool in ALLOW ALL mode - SECURITY RISK! {backend_info} "
            "Any command can be executed without restrictions."
        )

    # Add the shell tool to the tools list
    tools.append(shell_tool)
    logger.info(f"Added shell command execution tool to agent tools {backend_info}")

    # Create the agent with all the specified parameters and tools
    agent = create_agent(
        tools=tools, model=model, instruction_name=instruction_name, config=config
    )

    # Log tools information
    if agent and agent.root_agent and agent.root_agent.tools:
        tool_names = []
        for tool in agent.root_agent.tools:
            tool_name = getattr(tool, "name", None) or getattr(
                tool, "__name__", str(tool)
            )
            tool_names.append(tool_name)

        shell_tools = [
            t
            for t in tool_names
            if "shell" in t.lower() or "command" in t.lower() or "execute" in t.lower()
        ]
        if shell_tools:
            logger.info(f"Shell execution tools available: {', '.join(shell_tools)}")
        else:
            logger.warning("No shell execution tools found in the agent!")

    return agent


def create_shell_enabled_root_agent(
    model: Optional[str] = None,
    base_tools: Optional[List[Any]] = None,
    instruction_name: str = "main_agent",
    name: str = "shell_agent",
    config: Optional[ConfigManager] = None,
    strict_mode: bool = True,
    use_claude_cli: bool = False,
) -> Agent:
    """
    Create a root agent with shell command execution capabilities.

    This factory function creates an ADK Agent with shell command execution,
    with optional strict or allow-all mode.

    Args:
        model: Optional model to use
        base_tools: Optional list of base tools to include
        instruction_name: Name of instruction to load from config
        name: Name of the agent (default: "shell_agent")
        config: Optional ConfigManager instance
        strict_mode: When True, only allow-listed commands are permitted.
                    When False, any command can be executed (SECURITY RISK).
        use_claude_cli: Whether to use Claude CLI for command execution (default: False)

    Returns:
        An Agent with shell command execution capabilities
    """
    # Start with base tools or empty list
    tools = list(base_tools or [])

    # Create the shell command tool (now returns ADK-compatible FunctionTool)
    shell_tool = get_shell_tool(strict_mode=strict_mode, use_claude_cli=use_claude_cli)

    # Log security mode and execution backend
    if use_claude_cli:
        backend_info = "using Claude CLI backend"
    else:
        backend_info = "using subprocess backend"

    if strict_mode:
        logger.info(
            f"Adding shell command execution tool in STRICT mode (only allow-listed commands) {backend_info}"
        )
    else:
        logger.warning(
            f"Adding shell command execution tool in ALLOW ALL mode - SECURITY RISK! {backend_info} "
            "Any command can be executed without restrictions."
        )

    # Add the shell tool to the tools list
    tools.append(shell_tool)
    logger.info(f"Added shell command execution tool to agent tools {backend_info}")

    # Create the root agent
    root_agent = AgentFactory.create_root_agent(
        name=name,
        model=model,
        tools=tools,
        instruction_name=instruction_name,
        config=config,
    )

    return root_agent
