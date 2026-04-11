"""
Agent tools setup for RadBot.

This module handles the setup and initialization of the root agent (beto).
Beto is a pure orchestrator with only memory tools — all domain tools
are on specialized sub-agents created by specialized_agent_factory.py.
"""

import importlib
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

# Registry of DB schema initializers: (state_key, module_path, function_name)
_SCHEMA_INITS = [
    ("todo_init", "radbot.tools.todo", "init_database"),
    ("scheduler_init", "radbot.tools.scheduler", "init_scheduler_schema"),
    ("webhook_init", "radbot.tools.webhooks", "init_webhook_schema"),
    ("reminder_init", "radbot.tools.reminders", "init_reminder_schema"),
]


def setup_before_agent_call(callback_context: CallbackContext):
    """Setup agent before each call.

    Initializes all DB schemas on first invocation. These are idempotent
    (CREATE TABLE IF NOT EXISTS) and only run once per process.
    """
    global _process_initialized
    if _process_initialized:
        return

    for key, module_path, func_name in _SCHEMA_INITS:
        if key not in callback_context.state:
            try:
                mod = importlib.import_module(module_path)
                getattr(mod, func_name)()
                callback_context.state[key] = True
                label = key.replace("_init", "").replace("_", " ").title()
                logger.info(f"{label} database schema initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize {key}: {e}")
                callback_context.state[key] = False

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
