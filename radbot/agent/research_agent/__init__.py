"""
Research Agent package for technical research and design collaboration.

This subpackage provides a specialized agent for technical research and
rubber duck debugging sessions.
"""

from radbot.agent.research_agent.agent import ResearchAgent
from radbot.agent.research_agent.factory import create_research_agent

__all__ = ["create_research_agent", "ResearchAgent"]
