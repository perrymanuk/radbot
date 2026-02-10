"""
Factory function for creating the Axel execution agent.

This module provides the factory function for creating the Axel execution agent,
which is specialized for implementation tasks and complements the Scout agent.
"""

import logging
from typing import Any, List, Optional, Union

from google.adk.agents import Agent

from radbot.config import config_manager
from radbot.agent.execution_agent.agent import ExecutionAgent, AxelExecutionAgent

# Set up logging
logger = logging.getLogger(__name__)


def create_execution_agent(
    name: str = "axel",
    model: Optional[str] = None,
    custom_instruction: Optional[str] = None,
    tools: Optional[List[Any]] = None,
    as_subagent: bool = True,
    enable_code_execution: bool = True,
    app_name: str = "beto"
) -> Union[ExecutionAgent, Any]:
    """
    Create an execution agent with the specified configuration.
    
    Args:
        name: Name of the agent (should be "axel" for consistent transfers)
        model: LLM model to use (defaults to config setting)
        custom_instruction: Optional custom instruction to override the default
        tools: List of tools to provide to the agent
        as_subagent: Whether to return the ExecutionAgent or the underlying ADK agent
        enable_code_execution: Whether to enable Code Execution capability
        app_name: Application name (should match the parent agent name for ADK 0.4.0+)
        
    Returns:
        Union[ExecutionAgent, Any]: The created agent instance
    """
    # Use agent-specific model from config or fall back to default
    if model is None:
        model = config_manager.get_agent_model("axel_agent")
        logger.info(f"Using model from config for axel_agent: {model}")
    
    # Get the instruction file or use the provided custom instruction
    if custom_instruction:
        instruction = custom_instruction
        logger.info("Using provided custom instruction for Axel agent")
    else:
        try:
            instruction = config_manager.get_instruction("axel")
            logger.info("Using 'axel.md' instruction file for Axel agent")
        except FileNotFoundError:
            logger.warning("Instruction 'axel.md' not found, using minimal instruction")
            instruction = "You are Axel, a specialized execution agent focused on implementing specifications."
    
    # Create the tool list
    agent_tools = []
    if tools:
        agent_tools.extend(tools)

    # Note: transfer_to_agent is NOT added here explicitly — ADK auto-injects it
    # for any agent that is part of a sub_agents tree.

    # Add agent-scoped memory tools
    try:
        from radbot.tools.memory.agent_memory_factory import create_agent_memory_tools
        memory_tools = create_agent_memory_tools("axel")
        agent_tools.extend(memory_tools)
        logger.info("Added agent-scoped memory tools to Axel")
    except Exception as e:
        logger.warning(f"Failed to add memory tools to Axel: {e}")

    # Add filesystem tools via MCP
    try:
        from radbot.tools.mcp import create_fileserver_toolset
        fs_tools = create_fileserver_toolset()
        if fs_tools:
            agent_tools.extend(fs_tools)
            logger.info(f"Added {len(fs_tools)} filesystem tools to Axel")
    except Exception as e:
        logger.warning(f"Failed to add filesystem tools to Axel: {e}")

    # Add dynamic MCP tools
    try:
        from radbot.tools.mcp.dynamic_tools_loader import load_dynamic_mcp_tools
        mcp_tools = load_dynamic_mcp_tools()
        if mcp_tools:
            agent_tools.extend(mcp_tools)
            logger.info(f"Added {len(mcp_tools)} dynamic MCP tools to Axel")
    except Exception as e:
        logger.warning(f"Failed to add dynamic MCP tools to Axel: {e}")

    # Add artifacts loading tool
    try:
        from google.adk.tools import load_artifacts
        agent_tools.append(load_artifacts)
        logger.info("Added load_artifacts tool to Axel")
    except Exception as e:
        logger.warning(f"Failed to add load_artifacts to Axel: {e}")

    # Add code execution tool if enabled
    if enable_code_execution:
        try:
            from radbot.tools.shell import get_shell_tool
            shell_tool = get_shell_tool(strict_mode=True)
            agent_tools.append(shell_tool)
            logger.info("Added shell command execution tool to Axel agent")
        except Exception as e:
            logger.warning(f"Failed to add shell tool to Axel: {e}")
        logger.info("Code execution capability enabled for Axel agent")
    
    # Add transfer instructions
    transfer_instructions = (
        "\n\nIMPORTANT: When you have completed your task, you MUST use the transfer_to_agent tool "
        "to transfer back to beto. Call transfer_to_agent(agent_name='beto') to return control "
        "to the main agent. You can also transfer to scout for research tasks by calling "
        "transfer_to_agent(agent_name='scout')."
    )
    full_instruction = instruction + transfer_instructions

    # Create the ExecutionAgent instance
    execution_agent = ExecutionAgent(
        name=name,
        model=model,
        instruction=full_instruction,
        tools=agent_tools,
        enable_code_execution=enable_code_execution,
        app_name=app_name
    )

    logger.info(f"Created Axel execution agent with {len(agent_tools)} tools")

    # Return either the ExecutionAgent or the underlying ADK agent
    if as_subagent:
        # Create and return the ADK agent for use as a subagent
        adk_agent = Agent(
            name=name,
            model=model,
            description="A specialized agent for implementing code, executing tasks, and managing project files.",
            instruction=full_instruction,
            tools=agent_tools
        )
        
        # Store the execution_agent reference on the ADK agent for later access
        adk_agent._execution_agent = execution_agent
        
        logger.info(f"Returning ADK agent for {name} to use as subagent")
        return adk_agent
    else:
        # Return the ExecutionAgent wrapper
        logger.info(f"Returning ExecutionAgent wrapper for {name}")
        return execution_agent