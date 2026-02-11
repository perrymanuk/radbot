"""
Agent Tool functions for RadBot.

With the orchestrator architecture, beto delegates to sub-agents via ADK's
transfer_to_agent (auto-injected). This module is kept for backward
compatibility but the wrapper functions are no longer registered as tools
on the root agent.
"""

import logging

logger = logging.getLogger(__name__)

# These sync wrappers are kept for backward compatibility with tests
# and any code that imports them, but they are no longer registered as
# FunctionTools on any agent.


def _get_search_agent():
    """Lazily import the search agent to avoid circular imports."""
    from radbot.agent.agent_tools_setup import search_agent

    return search_agent


def _get_code_execution_agent():
    """Lazily import the code execution agent to avoid circular imports."""
    from radbot.agent.agent_tools_setup import code_execution_agent

    return code_execution_agent


def _get_scout_agent():
    """Lazily import the scout agent to avoid circular imports."""
    from radbot.agent.agent_tools_setup import scout_agent

    return scout_agent
