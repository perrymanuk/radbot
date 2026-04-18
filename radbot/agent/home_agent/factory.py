"""
Factory function for creating the Casa home agent.

Casa handles Home Assistant device control and Overseerr media requests.
"""

import logging
from typing import Optional

from google.adk.agents import Agent

from radbot.agent.factory_utils import load_tools
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

        # Home Assistant tools — prefer the native `mcp_server` integration
        # (HA 2025.2+): one streamable-HTTP client, all 19 built-in Assist
        # intents plus every user-exposed script, native fuzzy resolution
        # via name/area/floor/domain[]/device_class[]. Falls back to the
        # REST tool set only if MCP is disabled or unreachable.
        from radbot.config.config_loader import config_loader

        ha_config = config_loader.get_home_assistant_config()
        use_mcp = ha_config.get("use_mcp", True)

        ha_tools_loaded = False
        if use_mcp:
            try:
                from radbot.tools.homeassistant.ha_mcp_client import (
                    get_ha_mcp_client,
                )
                from radbot.tools.homeassistant.ha_mcp_tools import (
                    build_ha_mcp_function_tools,
                )

                mcp_client = get_ha_mcp_client()
                if mcp_client is not None:
                    mcp_tools = build_ha_mcp_function_tools(mcp_client)
                    if mcp_tools:
                        tools.extend(mcp_tools)
                        logger.info(
                            "Added %d Home Assistant MCP tools to Casa",
                            len(mcp_tools),
                        )
                        ha_tools_loaded = True
            except Exception as e:
                logger.warning(
                    "Failed to load HA MCP tools, will try REST fallback: %s", e
                )

        if not ha_tools_loaded:
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
                logger.info("Added 6 Home Assistant REST tools to Casa (fallback)")
            except Exception as e:
                logger.warning(f"Failed to add HA REST tools to Casa: {e}")

        # Dashboard tools (WebSocket-based)
        tools.extend(load_tools("radbot.tools.homeassistant", "HA_DASHBOARD_TOOLS", "Casa", "HA dashboard"))

        # Overseerr tools
        tools.extend(load_tools("radbot.tools.overseerr", "OVERSEERR_TOOLS", "Casa", "Overseerr"))

        # Lidarr music tools
        tools.extend(load_tools("radbot.tools.lidarr", "LIDARR_TOOLS", "Casa", "Lidarr"))

        # Picnic grocery tools
        tools.extend(load_tools("radbot.tools.picnic", "PICNIC_TOOLS", "Casa", "Picnic"))

        # Card-rendering tools (media, ha-device, season breakdown)
        tools.extend(load_tools("radbot.tools.shared.card_protocol", "CARD_TOOLS", "Casa", "cards"))

        # Agent-scoped memory tools
        from radbot.tools.memory.agent_memory_factory import create_agent_memory_tools

        memory_tools = create_agent_memory_tools("casa")
        tools.extend(memory_tools)

        agent = Agent(
            name="casa",
            model=model,
            description="Smart home device control (lights, switches, sensors), dashboard management (Lovelace), media requests (movies, TV shows), music collection (Lidarr), and grocery ordering (Picnic).",
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
