"""Transfer controller for specialized agents.

This module provides the TransferController class which manages transfers
between specialized agents according to the Modified Hub-and-Spoke Pattern
with Directed Transfers.
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Set

from google.adk.agents import Agent
from google.adk.tools.transfer_to_agent_tool import transfer_to_agent

from radbot.tools.specialized.base_toolset import (
    get_all_toolsets,
    get_allowed_transfers,
)

logger = logging.getLogger(__name__)


class TransferController:
    """Controls and manages transfers between specialized agents.

    This class implements the "Modified Hub-and-Spoke Pattern with Directed Transfers"
    architecture where a central orchestrator can transfer to any specialized agent,
    and specialized agents have specific allowed transfer targets.
    """

    def __init__(self):
        """Initialize the transfer controller."""
        self._agents: Dict[str, Agent] = {}
        self._main_agent: Optional[Agent] = None
        self._transfer_rules: Dict[str, Set[str]] = {}

    def register_main_agent(self, agent: Agent) -> None:
        """Register the main orchestrator agent.

        Args:
            agent: The main orchestrator agent instance
        """
        self._main_agent = agent
        self._agents[agent.name] = agent

        # Main agent can transfer to any specialized agent
        self._transfer_rules[agent.name] = set(self._agents.keys()) - {agent.name}
        logger.info(
            f"Registered main agent '{agent.name}' - can transfer to any specialized agent"
        )

    def register_specialized_agent(
        self,
        agent: Agent,
        specialization: str,
        allowed_transfers: Optional[List[str]] = None,
    ) -> None:
        """Register a specialized agent with the controller.

        Args:
            agent: The specialized agent instance
            specialization: The agent's specialization type
            allowed_transfers: Optional list of agent names this agent can transfer to
                              (overrides the default transfer rules from toolset registration)
        """
        self._agents[agent.name] = agent

        # Determine allowed transfers (configuration or defaults)
        if allowed_transfers is not None:
            # Use explicitly provided transfers
            self._transfer_rules[agent.name] = set(allowed_transfers)
        else:
            # Use transfers defined in the toolset registration
            try:
                self._transfer_rules[agent.name] = set(
                    get_allowed_transfers(specialization)
                )
            except ValueError:
                # No specific rules, so only allow transfer back to main agent
                self._transfer_rules[agent.name] = (
                    {self._main_agent.name} if self._main_agent else set()
                )

        # Always allow transfer back to main agent
        if (
            self._main_agent
            and self._main_agent.name not in self._transfer_rules[agent.name]
        ):
            self._transfer_rules[agent.name].add(self._main_agent.name)

        logger.info(
            f"Registered specialized agent '{agent.name}' with specialization '{specialization}' - "
            f"can transfer to: {', '.join(self._transfer_rules[agent.name])}"
        )

        # Update main agent's transfer rules to include this agent
        if (
            self._main_agent
            and agent.name not in self._transfer_rules[self._main_agent.name]
        ):
            self._transfer_rules[self._main_agent.name].add(agent.name)

    def create_transfer_tool(self, agent_name: str) -> Optional[Callable]:
        """Create a transfer tool customized for a specific agent.

        This creates an agent transfer tool that respects the transfer rules
        defined for the specified agent.

        Args:
            agent_name: Name of the agent to create the transfer tool for

        Returns:
            A transfer tool function that respects the architecture's transfer rules
        """
        if agent_name not in self._agents:
            logger.warning(
                f"Cannot create transfer tool for unknown agent '{agent_name}'"
            )
            return None

        # Get the allowed transfer targets for this agent
        allowed_targets = self._transfer_rules.get(agent_name, set())

        def transfer_with_rules(params: Dict[str, Any]) -> Dict[str, Any]:
            """Transfer to another agent, respecting the hub-and-spoke rules.

            Args:
                params: Dictionary with 'agent_name' and 'message' keys

            Returns:
                The response from the target agent or an error message
            """
            target_agent_name = params.get("agent_name")

            # Check if transfer is allowed
            if target_agent_name not in allowed_targets:
                error_msg = (
                    f"Transfer from '{agent_name}' to '{target_agent_name}' is not allowed. "
                    f"Allowed targets: {', '.join(allowed_targets)}"
                )
                logger.warning(error_msg)
                return {"error": error_msg}

            # Get the target agent
            target_agent = self._agents.get(target_agent_name)
            if not target_agent:
                error_msg = f"Target agent '{target_agent_name}' not found"
                logger.warning(error_msg)
                return {"error": error_msg}

            # Perform the transfer
            try:
                # Use the built-in transfer_to_agent tool but don't forward the original message
                # Instead, replace it with a neutral message to prevent context confusion between agents

                # Save original message but don't forward it
                original_message = params.get("message", "")
                logger.info(
                    f"Original transfer message (not forwarded): {original_message[:50]}..."
                )

                # Replace with a neutral initialization message that doesn't require a response
                # This ensures no context is carried from one agent to another
                params["message"] = f"Agent transfer initiated. Do not respond yet."

                # Perform the transfer with the modified message
                response = transfer_to_agent(params)
                logger.info(
                    f"Transferred from '{agent_name}' to '{target_agent_name}' with context separation"
                )

                # Return a standard greeting instead of forwarding the original prompt
                # This creates a clean context break between agents
                return {
                    "response": f"I am now {target_agent_name}. How can I help you today?"
                }
            except Exception as e:
                error_msg = f"Error transferring to '{target_agent_name}': {str(e)}"
                logger.error(error_msg)
                return {"error": error_msg}

        # Return the custom transfer function
        return transfer_with_rules

    def get_agent(self, agent_name: str) -> Optional[Agent]:
        """Get an agent by name.

        Args:
            agent_name: Name of the agent to retrieve

        Returns:
            The agent instance or None if not found
        """
        return self._agents.get(agent_name)

    def get_all_agents(self) -> Dict[str, Agent]:
        """Get all registered agents.

        Returns:
            Dictionary mapping agent names to agent instances
        """
        return self._agents.copy()

    def get_transfer_rules(self) -> Dict[str, List[str]]:
        """Get the transfer rules for all agents.

        Returns:
            Dictionary mapping agent names to lists of allowed transfer targets
        """
        return {agent: list(targets) for agent, targets in self._transfer_rules.items()}


# Create a singleton instance
transfer_controller = TransferController()


def get_transfer_controller() -> TransferController:
    """Get the singleton TransferController instance.

    Returns:
        The global TransferController instance
    """
    return transfer_controller
