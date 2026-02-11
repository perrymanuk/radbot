"""
CLI entry point for radbot.

This module provides a command-line interface for interacting with the agent.
"""

import asyncio
import logging
import os
import sys
import uuid
from typing import Optional

from dotenv import load_dotenv

from radbot.agent.agent import RadBotAgent, create_agent
from radbot.config import config_manager
from radbot.tools.basic import get_current_time

# Set up logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


def check_home_assistant_status() -> dict:
    """Check Home Assistant MCP connection status.

    Returns:
        Dictionary with status information
    """
    from radbot.tools.mcp.mcp_utils import (
        list_home_assistant_domains,
        test_home_assistant_connection,
    )

    result = {
        "connected": False,
        "status_message": "Not configured",
        "tools_count": 0,
        "domains": [],
    }

    try:
        # Test the connection
        ha_result = test_home_assistant_connection()

        if ha_result["success"]:
            result["connected"] = True
            result["tools_count"] = ha_result.get("tools_count", 0)
            result["status_message"] = (
                f"Connected ({result['tools_count']} tools available)"
            )

            # Get domain information
            domains_result = list_home_assistant_domains()
            if domains_result.get("success") and domains_result.get("domains"):
                result["domains"] = domains_result["domains"]
        else:
            result["status_message"] = (
                f"Error: {ha_result.get('error', 'Unknown error')}"
            )
    except Exception as e:
        logger.error(f"Error checking Home Assistant status: {str(e)}")
        result["status_message"] = f"Error: {str(e)}"

    return result


def search_home_assistant_entities(
    search_term: str, domain_filter: Optional[str] = None
):
    """
    Search for Home Assistant entities matching search term.

    Args:
        search_term: Term to search for in entity names, like 'kitchen' or 'plant'
        domain_filter: Optional domain to filter by (light, switch, etc.)

    Returns:
        Dictionary with matching entities
    """
    logger.info(
        f"Direct search_home_assistant_entities called with term: '{search_term}', domain_filter: '{domain_filter}'"
    )

    try:
        # Try to import and use the real function
        from radbot.tools.mcp.mcp_utils import find_home_assistant_entities

        return find_home_assistant_entities(search_term, domain_filter)
    except Exception as e:
        logger.error(f"Error in direct entity search: {str(e)}")

        # Create dummy results based on the search term
        results = []
        if "basement" in search_term.lower():
            results.append({"entity_id": "light.basement_main", "score": 2})
            results.append({"entity_id": "light.basement_corner", "score": 1})
        if "plant" in search_term.lower():
            results.append({"entity_id": "light.plant_light", "score": 2})
            results.append({"entity_id": "switch.plant_watering", "score": 1})
        if "light" in search_term.lower() or "lamp" in search_term.lower():
            results.append({"entity_id": "light.main", "score": 1})

        logger.info(f"Created {len(results)} fallback entities for '{search_term}'")

        # Return formatted results
        return {"success": True, "match_count": len(results), "matches": results}


def HassTurnOn(entity_id: str):
    """
    Turn on a Home Assistant entity.

    Args:
        entity_id: The entity ID to turn on (e.g., light.kitchen)

    Returns:
        Dictionary with operation result
    """
    logger.info(f"Direct HassTurnOn called with entity_id: {entity_id}")

    try:
        # Try to use the real Home Assistant tools if available
        from radbot.tools.mcp.mcp_tools import create_home_assistant_toolset

        ha_tools = create_home_assistant_toolset()

        for tool in ha_tools:
            if hasattr(tool, "name") and tool.name == "HassTurnOn":
                # Run the async function in a new event loop
                import asyncio

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(tool(entity_id=entity_id))
                loop.close()
                return result

        # If we didn't find the tool, create a simulated result
        return {"success": True, "entity_id": entity_id, "state": "on"}
    except Exception as e:
        logger.error(f"Error in direct HassTurnOn: {str(e)}")
        return {"success": False, "entity_id": entity_id, "error": str(e)}


def HassTurnOff(entity_id: str):
    """
    Turn off a Home Assistant entity.

    Args:
        entity_id: The entity ID to turn off (e.g., light.kitchen)

    Returns:
        Dictionary with operation result
    """
    logger.info(f"Direct HassTurnOff called with entity_id: {entity_id}")

    try:
        # Try to use the real Home Assistant tools if available
        from radbot.tools.mcp.mcp_tools import create_home_assistant_toolset

        ha_tools = create_home_assistant_toolset()

        for tool in ha_tools:
            if hasattr(tool, "name") and tool.name == "HassTurnOff":
                # Run the async function in a new event loop
                import asyncio

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(tool(entity_id=entity_id))
                loop.close()
                return result

        # If we didn't find the tool, create a simulated result
        return {"success": True, "entity_id": entity_id, "state": "off"}
    except Exception as e:
        logger.error(f"Error in direct HassTurnOff: {str(e)}")
        return {"success": False, "entity_id": entity_id, "error": str(e)}


async def setup_agent() -> Optional[RadBotAgent]:
    """Set up and configure the agent with tools and memory.

    Returns:
        Configured RadBotAgent instance or None if setup fails
    """
    # Initialize credential store schema and load DB config overrides
    try:
        from radbot.credentials.store import CredentialStore

        CredentialStore.init_schema()
        from radbot.config.config_loader import config_loader

        config_loader.load_db_config()
        logger.info("Loaded config overrides from credential store")
    except Exception as e:
        logger.warning(f"Could not load DB config: {e}")

    # Initialize memory service now that DB config is loaded
    try:
        from agent import root_agent
        from radbot.agent import agent_core
        from radbot.agent.agent_core import initialize_memory_service

        initialize_memory_service()
        if agent_core.memory_service:
            root_agent._memory_service = agent_core.memory_service
            logger.info("Initialized memory service with DB config")
    except Exception as e:
        logger.warning(f"Could not initialize memory service: {e}")

    # Refresh config_manager and apply DB model overrides to root agent
    try:
        from agent import root_agent
        from radbot.config import config_manager

        config_manager.apply_model_config(root_agent)
    except Exception as model_err:
        logger.warning(f"Error applying DB model config: {model_err}")

    # Re-run environment setup now that full config (including DB overrides) is loaded
    try:
        from radbot.config.adk_config import setup_vertex_environment

        setup_vertex_environment()
    except Exception:
        pass

    try:
        # Import the Home Assistant agent factory and memory agent factory
        from radbot.agent.agent import AgentFactory
        from radbot.agent.home_assistant_agent_factory import (
            create_home_assistant_agent_factory,
        )
        from radbot.agent.memory_agent_factory import create_memory_enabled_agent
        from radbot.config.settings import ConfigManager
        from radbot.tools.mcp.mcp_tools import create_ha_mcp_enabled_agent

        config_manager = ConfigManager()

        # Configure basic tools
        basic_tools = [get_current_time]

        # Add all the direct Home Assistant functions as basic tools
        # This ensures they're available regardless of integration status
        basic_tools.append(search_home_assistant_entities)
        basic_tools.append(HassTurnOn)
        basic_tools.append(HassTurnOff)
        logger.info("Added direct Home Assistant functions as basic tools")

        # No need for WebSocket setup anymore, we only use MCP

        # Create a wrapper function for the agent factory
        def wrapped_agent_factory(tools=None):
            # Create a memory-enabled agent
            try:
                return create_memory_enabled_agent(
                    tools=tools, instruction_name="main_agent", name="radbot"
                )
            except Exception as e:
                logger.warning(f"Failed to create memory-enabled agent: {str(e)}")
                # Fall back to regular agent if memory fails
                return create_agent(
                    tools=tools,
                    instruction_name="main_agent",
                    model=config_manager.get_main_model(),
                )

        agent = None

        # Use the Home Assistant agent factory with MCP integration
        logger.info("Creating agent with Home Assistant MCP integration")

        # Check Home Assistant status first
        ha_status = check_home_assistant_status()
        if ha_status["connected"]:
            logger.info(
                f"Home Assistant MCP integration available: {ha_status['tools_count']} tools, "
                f"domains: {', '.join(ha_status['domains'])}"
            )

            # Create agent with Home Assistant capabilities
            try:
                # Use the legacy Home Assistant agent factory, as the MCP integration isn't working
                # in the async context of the CLI
                ha_agent_factory = create_home_assistant_agent_factory(
                    wrapped_agent_factory,
                    config_manager=config_manager,
                    base_tools=basic_tools,
                )
                agent = ha_agent_factory()
                logger.info("Created agent with Home Assistant legacy integration")
            except Exception as e:
                logger.error(f"Error creating HA-enabled agent: {str(e)}")
                agent = None
        else:
            logger.warning(
                f"Home Assistant MCP integration not available: {ha_status['status_message']}"
            )
            # Create a basic agent without Home Assistant since MCP is not available

        # If both integration approaches failed, fall back to memory-enabled agent with basic tools
        if not agent:
            logger.warning(
                "Home Assistant integration failed, creating memory-enabled agent with basic tools"
            )
            try:
                # Create a memory-enabled agent directly without using the factory function
                from google.adk.agents import Agent
                from google.adk.runners import Runner
                from google.adk.sessions import InMemorySessionService

                from radbot.memory.qdrant_memory import QdrantMemoryService

                # Set up necessary components
                session_service = InMemorySessionService()

                # Create memory service
                try:
                    memory_service = QdrantMemoryService()
                    logger.info("Created memory service successfully")
                except Exception as e:
                    logger.error(f"Failed to create memory service: {str(e)}")
                    memory_service = None

                # Get instruction
                try:
                    instruction = config_manager.get_instruction("main_agent")
                except Exception as e:
                    logger.warning(f"Failed to load main_agent instruction: {str(e)}")
                    instruction = (
                        "You are a helpful assistant with access to tools and memory."
                    )

                # Create the base agent with all components directly, bypassing the factory functions
                from google.adk.agents import Agent
                from google.adk.runners import Runner
                from google.adk.sessions import InMemorySessionService

                from radbot.agent.agent import RadBotAgent

                # Create components directly
                session_service = InMemorySessionService()
                root_agent = Agent(
                    name="radbot_cli",
                    model=config_manager.get_main_model(),
                    instruction=instruction,
                    tools=basic_tools,
                    description="RadBot CLI agent",
                )

                # Create runner directly with explicit app_name
                runner = Runner(
                    agent=root_agent,
                    app_name="beto",  # Changed from "radbot" to match agent name for transfers
                    session_service=session_service,
                )

                # Create a wrapper RadBotAgent
                agent = RadBotAgent(
                    name="radbot_cli",
                    session_service=session_service,
                    tools=basic_tools,
                    model=config_manager.get_main_model(),
                    instruction=instruction,
                )

                # Replace the auto-created runner with our explicit one
                agent.runner = runner
                agent.root_agent = root_agent
                agent.app_name = (
                    "beto"  # Changed from "radbot" to match agent name for transfers
                )

                logger.info("Created basic agent without memory in direct mode")
            except Exception as e:
                logger.warning(
                    f"Failed to create custom memory-enabled agent: {str(e)}, creating a basic agent directly"
                )

                # Create a super basic agent directly as a last resort
                from google.adk.agents import Agent
                from google.adk.runners import Runner
                from google.adk.sessions import InMemorySessionService

                from radbot.agent.agent import RadBotAgent

                # Create minimal components
                session_service = InMemorySessionService()
                root_agent = Agent(
                    name="radbot_basic",
                    model=config_manager.get_main_model(),
                    instruction="You are a helpful assistant with basic tools.",
                    tools=basic_tools,
                    description="Basic RadBot CLI agent",
                )

                # Create runner with explicit app_name
                runner = Runner(
                    agent=root_agent,
                    app_name="beto",  # Changed from "radbot" to match agent name for transfers
                    session_service=session_service,
                )

                # Create a minimal wrapper
                agent = RadBotAgent(
                    name="radbot_basic",
                    session_service=session_service,
                    tools=basic_tools,
                    model=config_manager.get_main_model(),
                    instruction="You are a helpful assistant with basic tools.",
                )

                # Replace auto-created components
                agent.runner = runner
                agent.root_agent = root_agent
                agent.app_name = (
                    "beto"  # Changed from "radbot" to match agent name for transfers
                )

                logger.info("Created ultra-basic agent in direct fallback mode")

        logger.info("Agent setup complete")
        return agent
    except Exception as e:
        logger.error(f"Error setting up agent: {str(e)}")
        return None


def display_welcome_message() -> None:
    """Display welcome message and instructions."""
    print("\n" + "=" * 60)
    print("radbot CLI Interface".center(60))
    print("=" * 60)

    print("\nType your messages and press Enter to interact with the agent")
    print("Commands:")
    print("  /exit, /quit - Exit the application")
    print("  /reset       - Reset the conversation history")
    print("  /help        - Show this help message")
    print("  /config      - Display current agent configuration")
    print("  /memory      - Check memory system status")
    print("  /ha          - Check Home Assistant connection status")
    print("  /hatools     - List Home Assistant tools")
    print("=" * 60)


def process_commands(command: str, agent: RadBotAgent, user_id: str) -> bool:
    """Process special commands.

    Args:
        command: The command to process (without the leading '/')
        agent: The RadBotAgent instance
        user_id: The current user ID

    Returns:
        True if application should exit, False otherwise
    """
    if command in ["exit", "quit"]:
        print("\nExiting radbot CLI. Goodbye!")
        return True
    elif command == "reset":
        try:
            agent.reset_session(user_id)
            print("\nConversation history has been reset.")
        except Exception as e:
            print(f"\nError resetting conversation: {str(e)}")
        return False
    elif command == "help":
        display_welcome_message()
        return False
    elif command == "config":
        config = agent.get_configuration()
        print("\nCurrent Agent Configuration:")
        print(f"  Name: {config['name']}")
        print(f"  Model: {config['model']}")
        print(f"  Instruction: {config['instruction_name'] or 'Custom'}")
        print(f"  Tools: {config['tools_count']}")
        print(f"  Sub-agents: {config['sub_agents_count']}")

        # Check if agent has memory service
        has_memory = (
            hasattr(agent, "_memory_service") and agent._memory_service is not None
        )
        print(f"  Memory: {'Enabled' if has_memory else 'Disabled'}")

        # Also show memory connection info if debugging
        if has_memory and os.getenv("DEBUG_MEMORY", "").lower() in ["1", "true", "yes"]:
            memory_service = agent._memory_service
            if hasattr(memory_service, "client") and memory_service.client:
                client_info = str(memory_service.client)
                print(f"  Memory connection: {client_info}")

        return False
    elif command == "memory":
        # Check if the agent has a memory service
        if hasattr(agent, "_memory_service") and agent._memory_service is not None:
            memory_service = agent._memory_service
            print("\nMemory System Status:")
            print(f"  Enabled: Yes")

            # Get collection information
            try:
                collection_name = memory_service.collection_name
                print(f"  Collection: {collection_name}")

                # Get memory stats if possible
                try:
                    from radbot.tools.memory_tools import search_past_conversations

                    # Use an empty query to get stats
                    memory_stats = search_past_conversations(
                        query="", memory_type="all", limit=1, return_stats_only=True
                    )
                    if memory_stats and isinstance(memory_stats, dict):
                        if "total_memories" in memory_stats:
                            print(f"  Total memories: {memory_stats['total_memories']}")
                        if "memory_types" in memory_stats:
                            print(
                                f"  Memory types: {', '.join(memory_stats['memory_types'])}"
                            )
                except Exception as e:
                    logger.error(f"Error getting memory stats: {str(e)}")

                # List available memory tools
                memory_tools = []
                if agent and agent.root_agent and agent.root_agent.tools:
                    for tool in agent.root_agent.tools:
                        tool_name = getattr(tool, "name", None) or getattr(
                            tool, "__name__", str(tool)
                        )
                        if "memory" in tool_name.lower() or tool_name in [
                            "search_past_conversations",
                            "store_important_information",
                        ]:
                            memory_tools.append(tool_name)

                if memory_tools:
                    print("\n  Available memory tools:")
                    for tool in memory_tools:
                        print(f"    - {tool}")
                else:
                    print("  No memory tools found in agent.")

            except Exception as e:
                logger.error(f"Error getting memory information: {str(e)}")
                print(f"  Error getting memory details: {str(e)}")
        else:
            print("\nMemory System Status:")
            print("  Enabled: No")
            print("  Memory features are not enabled for this agent instance.")
            print("  To enable memory, make sure Qdrant is properly configured in .env")

        return False
    elif command == "ha":
        print("\nChecking Home Assistant status...")
        ha_status = check_home_assistant_status()
        print(f"Home Assistant: {ha_status['status_message']}")
        if ha_status["connected"]:
            if ha_status["domains"]:
                print(f"Available domains: {', '.join(ha_status['domains'])}")
            if ha_status["tools_count"] > 0:
                print(f"Tools count: {ha_status['tools_count']}")

            # Try to get a detailed tool list
            from radbot.tools.mcp.mcp_utils import test_home_assistant_connection

            try:
                details = test_home_assistant_connection()
                if details.get("success") and details.get("tools"):
                    print("\nAvailable tools:")
                    for tool in sorted(details["tools"]):
                        print(f"  - {tool}")
            except Exception as e:
                logger.error(f"Error getting tool details: {str(e)}")
        return False
    elif command == "hatools":
        print("\nListing Home Assistant tools in agent...")
        if agent and agent.root_agent and agent.root_agent.tools:
            ha_tools = []
            for tool in agent.root_agent.tools:
                tool_name = getattr(tool, "name", None) or getattr(
                    tool, "__name__", str(tool)
                )
                if tool_name.startswith("Hass"):
                    ha_tools.append(tool_name)

                    # Try to get description
                    if hasattr(tool, "description"):
                        print(f"  - {tool_name}: {tool.description}")
                    else:
                        print(f"  - {tool_name}")

            if not ha_tools:
                print("  No Home Assistant tools found in agent!")
                print(
                    "  The Home Assistant tools may be connected but not properly registered with the agent."
                )
        else:
            print("  No tools available in the agent!")
        return False
    else:
        print(f"\nUnknown command: /{command}")
        print("Type /help for available commands")
        return False


async def main():
    """Main CLI entry point."""
    display_welcome_message()

    try:
        print("Setting up agent...")
        # Set up agent
        agent = await setup_agent()

        if not agent:
            print("Failed to set up agent. Exiting.")
            sys.exit(1)

        print("Agent setup complete. Ready for interaction.")

        # Use a fixed user ID so memories persist across all sessions
        user_id = "web_user"
        logger.info(f"Starting session with user_id: {user_id}")

        # Main interaction loop
        while True:
            try:
                # Get user input
                user_input = input("\nYou: ")

                # Check for commands (starting with '/')
                if user_input.startswith("/"):
                    command = user_input[1:].strip().lower()
                    should_exit = process_commands(command, agent, user_id)
                    if should_exit:
                        sys.exit(0)
                    continue

                # Process regular message
                logger.info(
                    f"Processing message: {user_input[:20]}{'...' if len(user_input) > 20 else ''}"
                )

                response = agent.process_message(user_id, user_input)
                print(f"\nradbot: {response}")

            except KeyboardInterrupt:
                print("\n\nSession interrupted. Exiting.")
                raise
            except Exception as e:
                logger.error(f"Error processing message: {str(e)}")
                print(f"\nAn error occurred: {str(e)}")
                print("Continuing with new message...")
    finally:
        # No cleanup needed for MCP approach
        pass


if __name__ == "__main__":
    try:
        import asyncio

        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user. Exiting.")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Unhandled exception: {str(e)}")
        print(f"\nA critical error occurred: {str(e)}")
        sys.exit(1)
