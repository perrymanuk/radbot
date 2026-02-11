"""
Project-related tools for the Todo Tool.

This module defines the public functions for listing and managing projects.
"""

import logging
import traceback
from typing import Any, Dict

from google.adk.tools import FunctionTool

# Import database module functions
from ..db import get_db_connection
from ..db import list_projects as db_list_projects

# Setup logging
logger = logging.getLogger(__name__)

# --- Tool Function Implementations ---


def list_projects() -> Dict[str, Any]:
    """
    Retrieves a list of all available projects.

    This tool lists all projects that have been created in the database, including
    their UUIDs and names. This is useful for discovering available projects.

    Returns:
        A dictionary containing the list of projects or an error message.
        On success: {"status": "success", "projects": [{"id": "uuid", "name": "project_name", "created_at": "timestamp"},...]}
        On failure: {"status": "error", "message": "Concise error description..."}
    """
    try:
        with get_db_connection() as conn:
            projects = db_list_projects(conn)

            # Format project data for response
            project_list = []
            for proj in projects:
                project_list.append(
                    {
                        "id": str(proj.get("project_id")),
                        "name": proj.get("name"),
                        "created_at": (
                            proj.get("created_at").isoformat()
                            if proj.get("created_at")
                            else None
                        ),
                    }
                )

            # Create the response
            return {"status": "success", "projects": project_list}

    except Exception as e:
        error_message = f"Failed to list projects: {str(e)}"
        logger.error(f"Error in list_projects tool: {error_message}")
        logger.debug(traceback.format_exc())
        truncated_message = (
            (error_message[:197] + "...") if len(error_message) > 200 else error_message
        )
        return {"status": "error", "message": truncated_message}


# --- ADK Tool Wrapping ---
list_projects_tool = FunctionTool(list_projects)
