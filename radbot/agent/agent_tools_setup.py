"""
Agent tools setup for RadBot.

This module handles the setup and initialization of the root agent (beto).
Beto is a pure orchestrator with only memory tools — all domain tools
are on specialized sub-agents created by specialized_agent_factory.py.
"""

import logging
from typing import Any, List

from google.adk.agents.callback_context import CallbackContext

from radbot.config import config_manager

logger = logging.getLogger(__name__)

# Process-level flag — schema init and HA enumeration only need to run once
# per process, not once per session. The callback_context.state guard below
# is per-session (resets on every new WebSocket connection), so without this
# flag we'd fire 4 DB schema checks + an HA list_entities HTTP call on every
# new connection (~293 times in a typical E2E run).
_process_initialized = False


def setup_before_agent_call(callback_context: CallbackContext):
    """Setup agent before each call.

    Initializes all DB schemas on first invocation. These are idempotent
    (CREATE TABLE IF NOT EXISTS) and only run once per process.
    """
    global _process_initialized
    if _process_initialized:
        return

    # Initialize Todo database schema if needed
    if "todo_init" not in callback_context.state:
        try:
            from radbot.tools.todo import init_database

            init_database()
            callback_context.state["todo_init"] = True
            logger.info("Todo database schema initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Todo database: {str(e)}")
            callback_context.state["todo_init"] = False

    # Initialize Scheduler database schema if needed
    if "scheduler_init" not in callback_context.state:
        try:
            from radbot.tools.scheduler import init_scheduler_schema

            init_scheduler_schema()
            callback_context.state["scheduler_init"] = True
            logger.info("Scheduler database schema initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Scheduler database: {str(e)}")
            callback_context.state["scheduler_init"] = False

    # Initialize Webhook database schema if needed
    if "webhook_init" not in callback_context.state:
        try:
            from radbot.tools.webhooks import init_webhook_schema

            init_webhook_schema()
            callback_context.state["webhook_init"] = True
            logger.info("Webhook database schema initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Webhook database: {str(e)}")
            callback_context.state["webhook_init"] = False

    # Initialize Reminder database schema if needed
    if "reminder_init" not in callback_context.state:
        try:
            from radbot.tools.reminders import init_reminder_schema

            init_reminder_schema()
            callback_context.state["reminder_init"] = True
            logger.info("Reminder database schema initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Reminder database: {str(e)}")
            callback_context.state["reminder_init"] = False

    # Initialize Home Assistant client if not already done
    if "ha_client_init" not in callback_context.state:
        try:
            from radbot.tools.homeassistant import get_ha_client

            ha_client = get_ha_client()
            if ha_client:
                try:
                    entities = ha_client.list_entities()
                    if entities:
                        logger.info(
                            f"Successfully connected to Home Assistant. Found {len(entities)} entities."
                        )
                        callback_context.state["ha_client_init"] = True
                    else:
                        logger.warning(
                            "Connected to Home Assistant but no entities were returned"
                        )
                        callback_context.state["ha_client_init"] = False
                except Exception as e:
                    logger.error(f"Error testing Home Assistant connection: {e}")
                    callback_context.state["ha_client_init"] = False
            else:
                logger.warning("Home Assistant client could not be initialized")
                callback_context.state["ha_client_init"] = False
        except Exception as e:
            logger.error(f"Error initializing Home Assistant client: {e}")
            callback_context.state["ha_client_init"] = False

    # Mark process as initialized so subsequent sessions skip all the above
    _process_initialized = True
    logger.info("Process-level agent setup complete (schema init + HA check)")


from radbot.agent.research_agent.factory import create_research_agent
from radbot.tools.adk_builtin.code_execution_tool import create_code_execution_agent

# Create sub-agents that live directly under beto (not domain agents — those
# are created by specialized_agent_factory.py)
from radbot.tools.adk_builtin.search_tool import create_search_agent

search_agent = create_search_agent(name="search_agent")
code_execution_agent = create_code_execution_agent(name="code_execution_agent")
scout_agent = create_research_agent(name="scout", as_subagent=False)

# Attach empty content defense + telemetry callbacks to builtin sub-agents
try:
    from radbot.callbacks.empty_content_callback import (
        handle_empty_response_after_model,
        scrub_empty_content_before_model,
    )
    from radbot.callbacks.telemetry_callback import telemetry_after_model_callback

    _after_cbs = [handle_empty_response_after_model, telemetry_after_model_callback]
    for _sa in (search_agent, code_execution_agent, scout_agent):
        if _sa and not _sa.after_model_callback:
            _sa.after_model_callback = _after_cbs
        if _sa and not _sa.before_model_callback:
            _sa.before_model_callback = scrub_empty_content_before_model
except Exception:
    pass
