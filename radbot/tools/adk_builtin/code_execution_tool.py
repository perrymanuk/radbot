"""
Code Execution tool integration for ADK.

This module provides factory functions to create and register agents
that use the ADK code execution capability via generate_content_config.
"""

import logging
from typing import Optional, Any

from google.adk.agents import Agent, LlmAgent
from google.adk.code_executors import BuiltInCodeExecutor

from radbot.config import config_manager
from radbot.config.settings import ConfigManager

# Set up logging
logger = logging.getLogger(__name__)


def create_code_execution_agent(
    name: str = "code_execution_agent",
    model: Optional[str] = None,
    config: Optional[ConfigManager] = None,
    instruction_name: str = "code_execution_agent",
) -> Agent:
    """
    Create an agent with Code Execution capabilities.

    Args:
        name: Name for the agent (should be "code_execution_agent" for consistent transfers)
        model: Optional model override (defaults to config's main_model)
        config: Optional config manager (uses global if not provided)
        instruction_name: Name of instruction to load from config

    Returns:
        Agent with Code Execution tool
    """
    # Ensure agent name is always "code_execution_agent" for consistent transfers
    if name != "code_execution_agent":
        logger.warning(f"Agent name '{name}' changed to 'code_execution_agent' for consistent transfers")
        name = "code_execution_agent"

    # Use provided config or default
    cfg = config or config_manager

    # Get the model name (must be a Gemini 2 model)
    model_name = model or cfg.get_agent_model("code_execution_agent")
    if not any(n in model_name.lower() for n in ["gemini-2", "gemini-2.0", "gemini-2.5"]):
        logger.warning(
            f"Model {model_name} may not be compatible with code execution. "
            "Code Execution tool requires Gemini 2 models."
        )

    # Get the instruction
    try:
        instruction = cfg.get_instruction(instruction_name)
    except FileNotFoundError:
        logger.warning(
            f"Instruction '{instruction_name}' not found for code execution agent, "
            "using minimal instruction"
        )
        instruction = (
            "You are a code execution agent. You can help users by writing and executing "
            "Python code to perform calculations, data manipulation, or solve problems. "
            "When asked to write code, use the code_execution tool to run the code "
            "and return the results. Always explain the code you write and its output. "
            "When your task is complete, use the transfer_to_agent tool to transfer back to beto."
        )

    transfer_instructions = (
        "\n\nIMPORTANT: When you have completed your code execution task and provided the results, "
        "you MUST use the transfer_to_agent tool to transfer back to beto. "
        "Call transfer_to_agent(agent_name='beto') to return control to the main agent."
    )

    code_agent = Agent(
        name=name,
        model=model_name,
        instruction=instruction + transfer_instructions,
        description="A specialized agent that can execute Python code securely.",
        # Note: transfer_to_agent is auto-injected by ADK for sub_agents
        tools=[],
        code_executor=BuiltInCodeExecutor(),
    )

    logger.info(f"Created code execution agent '{name}' with code execution via generate_content_config")
    return code_agent


