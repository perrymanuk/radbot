"""
Factory function for creating the Casa home agent.

Casa handles Home Assistant device control and Overseerr media requests.
"""

import logging
from typing import Optional

from google.adk.agents import Agent

from radbot.agent.shared import load_agent_instruction, resolve_agent_model

logger = logging.getLogger(__name__)


def create_home_agent() -> Optional[Agent]:
    """Create the Casa agent for smart home and media control.

    Returns:
        The created Casa ADK Agent, or None if creation failed.
    """
    try:
        model = resolve_agent_model("casa_agent")
        logger.info(f"Casa agent model: {model}")

        instruction = load_agent_instruction(
            "casa",
            "You are Casa, a smart home and media specialist. "
            "Control Home Assistant devices and manage Overseerr media requests.",
        )

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

        # Dashboard tools (WebSocket-based)
        try:
            from radbot.tools.homeassistant import HA_DASHBOARD_TOOLS

            tools.extend(HA_DASHBOARD_TOOLS)
            logger.info(f"Added {len(HA_DASHBOARD_TOOLS)} HA dashboard tools to Casa")
        except Exception as e:
            logger.warning(f"Failed to add HA dashboard tools to Casa: {e}")

        # Overseerr tools
        try:
            from radbot.tools.overseerr import OVERSEERR_TOOLS

            tools.extend(OVERSEERR_TOOLS)
            logger.info(f"Added {len(OVERSEERR_TOOLS)} Overseerr tools to Casa")
        except Exception as e:
            logger.warning(f"Failed to add Overseerr tools to Casa: {e}")

        # Picnic grocery tools
        try:
            from radbot.tools.picnic import PICNIC_TOOLS

            tools.extend(PICNIC_TOOLS)
            logger.info(f"Added {len(PICNIC_TOOLS)} Picnic tools to Casa")
        except Exception as e:
            logger.warning(f"Failed to add Picnic tools to Casa: {e}")

        # Agent-scoped memory tools
        from radbot.tools.memory.agent_memory_factory import create_agent_memory_tools

        memory_tools = create_agent_memory_tools("casa")
        tools.extend(memory_tools)

        agent = Agent(
            name="casa",
            model=model,
            description="Smart home device control (lights, switches, sensors), dashboard management (Lovelace), media requests (movies, TV shows), and grocery ordering (Picnic).",
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
