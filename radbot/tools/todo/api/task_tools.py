"""
Task-related tools for the Todo Tool.

This module defines the public functions for adding, completing, and removing tasks.
"""

import uuid
import traceback
import logging
from typing import Optional, Dict, Any
from google.adk.tools import FunctionTool

# Import database and model modules
from ..db import get_db_connection, add_task as db_add_task, complete_task as db_complete_task, remove_task as db_remove_task, get_or_create_project_id

# Setup logging
logger = logging.getLogger(__name__)

# --- Tool Function Implementations ---

def add_task(description: str, project_id: str, title: Optional[str] = None,
             category: Optional[str] = None,
             origin: Optional[str] = None, related_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Adds a new todo task to the persistent database.

    This tool creates a new task entry with the provided details. It requires
    a description and either a project ID (UUID) or a project name. If a project name
    is provided, the tool will automatically look up or create a project with that name.

    Args:
        description: The main text content describing the task. (Required)
        project_id: The project ID or name the task belongs to. Can be a UUID string or a project name. (Required)
        title: An optional short summary for the task, displayed in the task list.
        category: An optional label to categorize the task (e.g., 'work', 'personal').
        origin: An optional string indicating the source of the task (e.g., 'chat', 'email', 'manual').
        related_info: An optional dictionary for storing supplementary structured data,
                      such as {'link': 'http://example.com', 'notes': 'Further details...'}.

    Returns:
        A dictionary indicating the outcome.
        On success: {"status": "success", "task_id": "new_task_uuid_string"}
        On failure: {"status": "error", "message": "Concise error description..."}
    """
    try:
        # Connect to database
        with get_db_connection() as conn:
            # Check if project_id is a UUID or a name
            try:
                # Try to parse as UUID
                project_uuid = uuid.UUID(project_id)
            except ValueError:
                # Not a valid UUID, treat as project name
                logger.info(f"Project ID '{project_id}' is not a UUID, treating as project name")
                project_uuid = get_or_create_project_id(conn, project_id)
                logger.info(f"Using project ID: {project_uuid} for project name: {project_id}")

            # Now add the task with the resolved project UUID
            # Convert project_uuid to string format for database operations
            new_task_id = db_add_task(
                conn=conn,
                description=description,
                project_id=project_uuid,  # UUID objects should now be handled correctly with the adapter
                category=category,
                origin=origin,
                related_info=related_info,
                title=title
            )
            
            # Log the task creation for debugging
            logger.debug(f"Created task with ID: {new_task_id} for project: {project_uuid}")
            
        # Create response with string UUID
        return {
            "status": "success",
            "task_id": str(new_task_id)
        }

    except Exception as e:
        # Handle error (logging, truncation, formatting)
        error_message = f"Failed to add task: {str(e)}"
        logger.error(f"Error in add_task tool: {error_message}")
        logger.debug(traceback.format_exc())  # Log full traceback for debugging
        truncated_message = (error_message[:197] + '...') if len(error_message) > 200 else error_message

        # Return error response directly
        return {
            "status": "error",
            "message": truncated_message
        }


def complete_task(task_id: str) -> Dict[str, Any]:
    """
    Marks a specific todo task as 'done'.

    Updates the status of the task identified by the given UUID to 'done'.

    Args:
        task_id: The UUID identifier of the task to mark as completed. (Required)

    Returns:
        A dictionary indicating the outcome.
        On success: {"status": "success", "task_id": "completed_task_uuid_string"}
        On failure: {"status": "error", "message": "Concise error description..."}
                    (e.g., if the task ID doesn't exist)
    """
    try:
        # Convert task_id string to UUID object
        try:
            task_uuid = uuid.UUID(task_id)
        except ValueError:
            return {
                "status": "error",
                "message": f"Invalid task ID format: {task_id}. Must be a valid UUID."
            }

        with get_db_connection() as conn:
            success = db_complete_task(conn, task_uuid)

        if success:
            return {
                "status": "success",
                "task_id": str(task_uuid)
            }
        else:
            # Task not found or already done (depending on desired logic)
            return {
                "status": "error",
                "message": f"Task with ID {task_id} not found or could not be updated."
            }

    except Exception as e:
        error_message = f"Failed to complete task {task_id}: {str(e)}"
        logger.error(f"Error in complete_task tool: {error_message}")
        logger.debug(traceback.format_exc())
        truncated_message = (error_message[:197] + '...') if len(error_message) > 200 else error_message
        return {
            "status": "error",
            "message": truncated_message
        }


def remove_task(task_id: str) -> Dict[str, Any]:
    """
    Permanently deletes a specific todo task from the database.

    Removes the task identified by the given UUID. This action cannot be undone.

    Args:
        task_id: The UUID identifier of the task to delete. (Required)

    Returns:
        A dictionary indicating the outcome.
        On success: {"status": "success", "task_id": "deleted_task_uuid_string"}
        On failure: {"status": "error", "message": "Concise error description..."}
                    (e.g., if the task ID doesn't exist)
    """
    try:
        # Convert task_id string to UUID object
        try:
            task_uuid = uuid.UUID(task_id)
            logger.debug(f"Successfully parsed task_id {task_id} as UUID: {task_uuid}")
        except ValueError:
            return {
                "status": "error",
                "message": f"Invalid task ID format: {task_id}. Must be a valid UUID."
            }

        # Log the UUID type and value before using it
        logger.debug(f"Removing task with UUID type: {type(task_uuid)}, value: {task_uuid}")

        # Get connection and attempt to remove the task
        with get_db_connection() as conn:
            try:
                success = db_remove_task(conn, task_uuid)
                
                if success:
                    logger.info(f"Successfully removed task with ID: {task_uuid}")
                    return {
                        "status": "success",
                        "task_id": str(task_uuid)
                    }
                else:
                    # Task not found
                    logger.warning(f"Task with ID {task_uuid} not found for deletion")
                    return {
                        "status": "error",
                        "message": f"Task with ID {task_id} not found for deletion."
                    }
            except Exception as db_error:
                logger.error(f"Database error in db_remove_task: {db_error}")
                return {
                    "status": "error",
                    "message": f"Database error: {str(db_error)}"
                }

    except Exception as e:
        error_message = f"Failed to remove task {task_id}: {str(e)}"
        logger.error(f"Error in remove_task tool: {error_message}")
        logger.debug(traceback.format_exc())
        truncated_message = (error_message[:197] + '...') if len(error_message) > 200 else error_message
        return {
            "status": "error",
            "message": truncated_message
        }

# --- ADK Tool Wrapping ---
add_task_tool = FunctionTool(add_task)
complete_task_tool = FunctionTool(complete_task)
remove_task_tool = FunctionTool(remove_task)
