"""
Factory function for creating the Casa home agent.

Casa handles Home Assistant device control and Overseerr media requests.
"""

import logging
from typing import Optional

from google.adk.agents import Agent

from radbot.config import config_manager

logger = logging.getLogger(__name__)

TRANSFER_INSTRUCTIONS = (
    "\n\nCRITICAL RULE — Returning control:\n"
    "1. First, complete your task using your tools and compose your full text response with the results.\n"
    "2. Then, call transfer_to_agent(agent_name='beto') to return control to the main agent.\n"
    "You MUST always do BOTH steps — never return without text content, and never skip the transfer back."
)


def create_home_agent() -> Optional[Agent]:
    """Create the Casa agent for smart home and media control.

    Returns:
        The created Casa ADK Agent, or None if creation failed.
    """
    try:
        # Get model and resolve (wraps Ollama models in LiteLlm)
        model_str = config_manager.get_agent_model("casa_agent")
        if not model_str:
            model_str = config_manager.get_sub_model()
        model = config_manager.resolve_model(model_str)
        logger.info(f"Casa agent model: {model_str}")

        # Get instruction
        try:
            instruction = config_manager.get_instruction("casa")
        except FileNotFoundError:
            instruction = (
                "You are Casa, a smart home and media specialist. "
                "Control Home Assistant devices and manage Overseerr media requests."
            )
        instruction += TRANSFER_INSTRUCTIONS

        # Build tools list
        tools = []

        # Home Assistant tools
        try:
            from radbot.tools.homeassistant import (
                get_ha_entity_state,
                list_ha_entities,
                search_ha_entities,
                toggle_ha_entity,
                turn_off_ha_entity,
                turn_on_ha_entity,
            )

            tools.extend(
                [
                    search_ha_entities,
                    list_ha_entities,
                    get_ha_entity_state,
                    turn_on_ha_entity,
                    turn_off_ha_entity,
                    toggle_ha_entity,
                ]
            )
            logger.info("Added 6 Home Assistant tools to Casa")
        except Exception as e:
            logger.warning(f"Failed to add HA tools to Casa: {e}")

        # Overseerr tools
        try:
            from radbot.tools.overseerr import OVERSEERR_TOOLS

            tools.extend(OVERSEERR_TOOLS)
            logger.info(f"Added {len(OVERSEERR_TOOLS)} Overseerr tools to Casa")
        except Exception as e:
            logger.warning(f"Failed to add Overseerr tools to Casa: {e}")

        # Agent-scoped memory tools
        from radbot.tools.memory.agent_memory_factory import create_agent_memory_tools

        memory_tools = create_agent_memory_tools("casa")
        tools.extend(memory_tools)

        agent = Agent(
            name="casa",
            model=model,
            description="Smart home device control (lights, switches, sensors) and media requests (movies, TV shows).",
            instruction=instruction,
            tools=tools,
        )

        logger.info(f"Created Casa agent with {len(tools)} tools")
        return agent

    except Exception as e:
        logger.error(f"Failed to create Casa agent: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return None
