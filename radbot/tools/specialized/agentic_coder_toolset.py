"""Agentic coder toolset for specialized agents.

This module provides tools for delegating to other models and
processing responses for agent-to-agent communication.
"""

import logging
from typing import Any, List, Optional

# Import Claude prompt tool
try:
    from radbot.tools.claude_prompt import prompt_claude
except ImportError:
    prompt_claude = None

# Import tools for model/agent delegation
try:
    from radbot.tools.mcp.claude_cli import prompt_claude_mcp
except ImportError:
    prompt_claude_mcp = None

# Import direct Claude CLI tool if available
try:
    from radbot.tools.mcp.direct_claude_cli import direct_prompt_claude
except ImportError:
    direct_prompt_claude = None

# Import base toolset for registration
from .base_toolset import register_toolset

logger = logging.getLogger(__name__)


def create_agentic_coder_toolset() -> List[Any]:
    """Create the set of tools for the agentic coder specialized agent.

    Returns:
        List of tools for delegating to models and processing responses
    """
    toolset = []

    # Add Claude prompt tool
    if prompt_claude:
        try:
            toolset.append(prompt_claude)
            logger.info("Added prompt_claude to agentic coder toolset")
        except Exception as e:
            logger.error(f"Failed to add prompt_claude: {e}")

    # Add MCP-based Claude prompt tool
    if prompt_claude_mcp:
        try:
            toolset.append(prompt_claude_mcp)
            logger.info("Added prompt_claude_mcp to agentic coder toolset")
        except Exception as e:
            logger.error(f"Failed to add prompt_claude_mcp: {e}")

    # Add direct Claude CLI tool
    if direct_prompt_claude:
        try:
            toolset.append(direct_prompt_claude)
            logger.info("Added direct_prompt_claude to agentic coder toolset")
        except Exception as e:
            logger.error(f"Failed to add direct_prompt_claude: {e}")

    # Add Context7 MCP tools if available
    try:
        from radbot.tools.mcp.context7_client import get_context7_tools

        if get_context7_tools:
            context7_tools = get_context7_tools()
            if context7_tools:
                toolset.extend(context7_tools)
                logger.info(
                    f"Added {len(context7_tools)} Context7 tools to agentic coder toolset"
                )
    except Exception as e:
        logger.error(f"Failed to add Context7 tools: {e}")

    return toolset


# Register the toolset with the system
register_toolset(
    name="agentic_coder",
    toolset_func=create_agentic_coder_toolset,
    description="Agent specialized in delegating to other models and processing responses",
    allowed_transfers=[],  # Only allows transfer back to main orchestrator
)
