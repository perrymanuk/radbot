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


# HA tools currently installed on the live casa agent. Tracked so
# `refresh_home_assistant_tools()` can swap them out in place after an
# admin-UI change to the HA URL / token / use_mcp flag.
_installed_ha_tools: list = []


def _build_ha_tools() -> list:
    """Build the Home Assistant tool set from the *current* merged config.

    Prefers the native `mcp_server` integration (HA 2025.2+): one
    streamable-HTTP client, all 19 built-in Assist intents plus every
    user-exposed script, native fuzzy resolution via
    name/area/floor/domain[]/device_class[]. Falls back to the REST tool set
    if MCP is disabled (``integrations.home_assistant.use_mcp`` is off by
    default) or unreachable.
    """
    from radbot.config.config_loader import config_loader

    tools: list = []
    ha_config = config_loader.get_home_assistant_config()
    use_mcp = ha_config.get("use_mcp", False)

    if use_mcp:
        try:
            from radbot.clients.provider import get_provider
            from radbot.tools.homeassistant.ha_mcp_tools import (
                build_ha_mcp_function_tools,
            )

            mcp_client = get_provider().ha_mcp
            if mcp_client is not None:
                mcp_tools = build_ha_mcp_function_tools(mcp_client)
                if mcp_tools:
                    logger.info(
                        "Added %d Home Assistant MCP tools to Casa", len(mcp_tools)
                    )
                    return list(mcp_tools)
        except Exception as e:
            logger.warning("Failed to load HA MCP tools, will try REST fallback: %s", e)

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
    return tools


def refresh_home_assistant_tools(agent: Optional[Agent] = None) -> int:
    """Rebuild casa's HA tools from current config and swap them in place.

    The HA MCP tool list is fetched from HA and bound to a client at build
    time, so resetting the client singleton alone is not enough after the
    URL / token / use_mcp flag changes in the admin UI — the live agent
    keeps whatever it got at startup (typically the REST fallback if HA was
    unreachable then). Called from the admin hot-reload path.

    Returns the number of HA tools now installed (0 if casa isn't built).
    """
    if agent is None:
        try:
            from radbot.agent.assembly import _resolve_assembly

            agent = _resolve_assembly().root_agent.find_sub_agent("casa")
        except Exception as e:
            logger.debug("refresh_home_assistant_tools: no assembly yet (%s)", e)
            return 0
    if agent is None:
        return 0

    new_tools = _build_ha_tools()
    old_ids = {id(t) for t in _installed_ha_tools}
    remaining = [t for t in agent.tools if id(t) not in old_ids]
    # ADK reads `agent.tools` on every request, so an in-place swap takes
    # effect on the next LLM call without rebuilding the assembly.
    agent.tools[:] = new_tools + remaining
    _installed_ha_tools[:] = new_tools
    logger.info(
        "Refreshed casa HA tools: %d installed (%d total tools)",
        len(new_tools),
        len(agent.tools),
    )
    return len(new_tools)


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
            use_task_mode=True,
        )

        # Build tools list
        tools = []

        ha_tools = _build_ha_tools()
        tools.extend(ha_tools)
        _installed_ha_tools[:] = ha_tools

        # Dashboard tools (WebSocket-based)
        tools.extend(
            load_tools(
                "radbot.tools.homeassistant",
                "HA_DASHBOARD_TOOLS",
                "Casa",
                "HA dashboard",
            )
        )

        # Overseerr tools
        tools.extend(
            load_tools("radbot.tools.overseerr", "OVERSEERR_TOOLS", "Casa", "Overseerr")
        )

        # Lidarr music tools
        tools.extend(
            load_tools("radbot.tools.lidarr", "LIDARR_TOOLS", "Casa", "Lidarr")
        )

        # Picnic grocery tools
        tools.extend(
            load_tools("radbot.tools.picnic", "PICNIC_TOOLS", "Casa", "Picnic")
        )

        # Card-rendering tools (media, ha-device, season breakdown)
        tools.extend(
            load_tools(
                "radbot.tools.shared.card_protocol", "CARD_TOOLS", "Casa", "cards"
            )
        )

        # Agent-scoped memory tools
        from radbot.tools.memory.agent_memory_factory import create_agent_memory_tools

        memory_tools = create_agent_memory_tools("casa")
        tools.extend(memory_tools)

        agent = Agent(
            name="casa",
            model=model,
            description="Smart home device control (lights, switches, sensors), dashboard management (Lovelace), media requests (movies, TV shows), music collection (Lidarr), and grocery ordering (Picnic).",  # noqa: E501
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
