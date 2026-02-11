"""
Execution agent module for Axel, a specialized agent for implementation tasks.

This module provides the implementation of the Axel execution agent, which
is designed to implement specifications created by the Scout research agent.
"""

from radbot.agent.execution_agent.agent import ExecutionAgent
from radbot.agent.execution_agent.factory import create_execution_agent

__all__ = ["ExecutionAgent", "create_execution_agent"]
