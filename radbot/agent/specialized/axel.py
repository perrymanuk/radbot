"""
Axel specialized agent implementation.

This module defines the Axel agent, which specializes in implementation and execution
of designs created by Scout.
"""

import logging
from typing import Any, Dict, List, Optional

from google.adk.agents import Agent
from google.adk.tools.function_tool import FunctionTool

from radbot.agent.agent_factory import AgentFactory
from radbot.tools.specialized.simple_axel_toolset import create_simple_axel_toolset
from radbot.tools.specialized.transfer_controller import get_transfer_controller

logger = logging.getLogger(__name__)


class AxelAgent:
    """Implementation of the Axel specialized agent."""

    @staticmethod
    def create_axel_agent(
        name: str = "axel_agent",
        model: Optional[str] = None,
        register_with_transfer_controller: bool = True,
    ) -> Agent:
        """Create the Axel specialized agent with implementation focus.

        Args:
            name: Name for the agent
            model: Optional model override
            register_with_transfer_controller: Whether to register with the transfer controller

        Returns:
            Configured Axel agent
        """
        # Get the agent toolset
        tools = create_simple_axel_toolset()

        # Create the agent
        agent = AgentFactory.create_sub_agent(
            name=name,
            description="Agent specialized in implementation and execution",
            instruction_name="axel",
            tools=tools,
            model=model,
        )

        # Register with transfer controller if requested
        if register_with_transfer_controller:
            transfer_controller = get_transfer_controller()
            transfer_controller.register_specialized_agent(
                agent=agent,
                specialization="axel",
                allowed_transfers=["scout_agent", "code_execution_agent"],
            )

            # Add the custom transfer tool
            transfer_tool = transfer_controller.create_transfer_tool(name)
            if transfer_tool and isinstance(transfer_tool, FunctionTool):
                # Remove existing transfer_to_agent if it exists
                for i, tool in enumerate(agent.tools):
                    if getattr(tool, "name", None) == "transfer_to_agent":
                        agent.tools.pop(i)
                        break

                # Add our custom transfer tool
                agent.tools.append(transfer_tool)
                logger.info(f"Added custom transfer tool to {name}")

        return agent

    @staticmethod
    def create_worker_agent(
        index: int,
        parent_agent: Optional[Agent] = None,
        task_description: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Agent:
        """Create a worker agent for parallel task execution.

        Args:
            index: Worker index (used to generate the name)
            parent_agent: Optional parent Axel agent
            task_description: Optional specific task description
            model: Optional model override

        Returns:
            Configured worker agent
        """
        # Generate worker name
        name = f"thing{index}"

        # Generate description
        description = task_description or f"Worker {index} for Axel agent"

        # Select a simpler toolset for workers
        # For now, just use the same toolset with reduced capabilities
        tools = create_simple_axel_toolset()

        # Create the worker agent
        worker = AgentFactory.create_sub_agent(
            name=name,
            description=description,
            instruction_name="axel",  # Use same instructions for simplicity
            tools=tools,
            model=model,
        )

        # Connect to parent if provided
        if parent_agent:
            parent_agent.add_sub_agent(worker)

        return worker
