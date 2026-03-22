"""
RadBot - A modular AI agent framework using Google ADK, Qdrant, MCP, and A2A.
"""

__version__ = "0.1.0"

try:
    from radbot.agent import RadBotAgent, create_agent, create_memory_enabled_agent
except ImportError:
    # Worker image doesn't include the agent module — that's fine.
    pass
