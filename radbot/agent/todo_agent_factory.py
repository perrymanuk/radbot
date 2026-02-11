"""
Factory module for creating a todo agent with persistence.

This module provides a factory function to create a Google ADK agent
with the todo tools for persistent task management.
"""

import logging

from google.adk.agents import Agent

from radbot.config import ConfigManager
from radbot.tools.todo.todo_tools import ALL_TOOLS, init_database

logger = logging.getLogger(__name__)


def create_todo_agent(name: str = "todo_agent", base_instruction: str = None) -> Agent:
    """
    Create an Agent with todo list tools for persistent task management.

    This factory initializes the PostgreSQL database schema if needed and
    creates an agent with all the necessary tools for managing a persistent
    todo list.

    Args:
        name: A name for the agent.
        base_instruction: Optional base instruction to include in the agent's instruction.
                        If not provided, a default instruction will be used.

    Returns:
        An ADK Agent configured with todo tools.
    """
    # Initialize the database schema if it doesn't exist
    try:
        init_database()
    except Exception as e:
        logger.error(f"Failed to initialize todo database: {e}")
        raise

    config = ConfigManager()

    # Define the instruction for the todo agent
    default_instruction = """
    You are a helpful assistant that can manage a persistent todo list for the user.
    You can add new tasks, list existing tasks, mark tasks as complete, and remove tasks.
    
    Use the add_task tool to create new tasks. You must provide a description and project_id.
    Project IDs should be UUIDs. When the user first mentions a project, generate a new UUID for it
    and remember this UUID for future interactions related to this project.
    
    Use the list_tasks tool to retrieve tasks for a specific project. You can optionally filter
    by status ('backlog', 'inprogress', 'done').
    
    Use the complete_task tool to mark a task as done. You need the task's UUID.
    
    Use the remove_task tool to permanently delete a task. This cannot be undone.
    
    Always confirm actions with the user, and provide helpful feedback about the results of todo operations.
    Keep track of project IDs for the user so they don't need to remember them.
    """

    instruction = base_instruction if base_instruction else default_instruction

    # Create the agent with todo tools
    agent = Agent(
        name=name,
        model=config.get_model_name(),
        description="An agent capable of managing a persistent todo list stored in a PostgreSQL database.",
        instruction=instruction,
        tools=ALL_TOOLS,
    )

    logger.info(f"Created todo agent with name: {name}")
    return agent
