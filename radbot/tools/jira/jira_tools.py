"""
Agent tools for Jira Cloud issue management.

Provides tools to list, inspect, transition, comment on, and search Jira
issues.  All tools return ``{"status": "success", ...}`` or
``{"status": "error", "message": ...}`` per project convention.
"""

import logging
import traceback
from typing import Any, Dict, List, Optional

from google.adk.tools import FunctionTool

from .jira_client import get_jira_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _format_issue(issue: Dict[str, Any], base_url: str = "") -> Dict[str, Any]:
    """Normalise a raw Jira API issue dict into a compact representation."""
    fields = issue.get("fields", {})

    def _name(obj):
        if obj is None:
            return None
        if isinstance(obj, dict):
            return obj.get("displayName") or obj.get("name")
        return str(obj)

    key = issue.get("key", "")
    return {
        "key": key,
        "summary": fields.get("summary"),
        "status": _name(fields.get("status")),
        "priority": _name(fields.get("priority")),
        "type": _name(fields.get("issuetype")),
        "assignee": _name(fields.get("assignee")),
        "reporter": _name(fields.get("reporter")),
        "created": fields.get("created"),
        "updated": fields.get("updated"),
        "url": f"{base_url.rstrip('/')}/browse/{key}" if base_url else key,
    }


def _client_or_error():
    """Return (client, None) or (None, error_dict)."""
    client = get_jira_client()
    if client is None:
        return None, {
            "status": "error",
            "message": (
                "Jira is not configured. Set integrations.jira in config.yaml "
                "or JIRA_URL/JIRA_EMAIL/JIRA_API_TOKEN environment variables."
            ),
        }
    return client, None


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------

def list_my_jira_issues(
    project: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    max_results: int = 20,
) -> Dict[str, Any]:
    """
    List Jira issues assigned to the current user.

    Args:
        project: Optional project key to filter by (e.g. "PROJ").
        status: Optional status name to filter by (e.g. "In Progress").
        priority: Optional priority name to filter by (e.g. "High").
        max_results: Maximum number of issues to return (default 20, max 50).

    Returns:
        On success: {"status": "success", "issues": [...], "total": N}
        On failure: {"status": "error", "message": "..."}
    """
    client, err = _client_or_error()
    if err:
        return err

    try:
        max_results = min(max(1, max_results), 50)

        jql_parts = ["assignee = currentUser()"]
        if project:
            jql_parts.append(f'project = "{project}"')
        if status:
            jql_parts.append(f'status = "{status}"')
        if priority:
            jql_parts.append(f'priority = "{priority}"')

        jql = " AND ".join(jql_parts) + " ORDER BY updated DESC"
        logger.debug("list_my_jira_issues JQL: %s", jql)

        result = client.jql(jql, limit=max_results)
        base_url = client.url

        issues = [_format_issue(i, base_url) for i in result.get("issues", [])]
        return {
            "status": "success",
            "issues": issues,
            "total": result.get("total", len(issues)),
        }
    except Exception as e:
        msg = f"Failed to list Jira issues: {e}"
        logger.error(msg)
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": msg[:300]}


def get_jira_issue(issue_key: str) -> Dict[str, Any]:
    """
    Get full details of a specific Jira issue.

    Args:
        issue_key: The issue key (e.g. "PROJ-123").

    Returns:
        On success: {"status": "success", "issue": {...}}
        On failure: {"status": "error", "message": "..."}
    """
    client, err = _client_or_error()
    if err:
        return err

    try:
        issue = client.issue(issue_key)
        base_url = client.url
        formatted = _format_issue(issue, base_url)

        # Add extra detail fields
        fields = issue.get("fields", {})
        formatted["description"] = fields.get("description")
        formatted["labels"] = fields.get("labels", [])
        formatted["components"] = [
            c.get("name") for c in (fields.get("components") or [])
        ]
        formatted["fix_versions"] = [
            v.get("name") for v in (fields.get("fixVersions") or [])
        ]
        formatted["comment_count"] = (
            fields.get("comment", {}).get("total", 0)
        )

        return {"status": "success", "issue": formatted}
    except Exception as e:
        msg = f"Failed to get Jira issue {issue_key}: {e}"
        logger.error(msg)
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": msg[:300]}


def get_issue_transitions(issue_key: str) -> Dict[str, Any]:
    """
    List available status transitions for a Jira issue.

    You should call this before transitioning an issue to know which target
    statuses are valid.

    Args:
        issue_key: The issue key (e.g. "PROJ-123").

    Returns:
        On success: {"status": "success", "issue_key": "...", "transitions": [{"id": "...", "name": "..."}]}
        On failure: {"status": "error", "message": "..."}
    """
    client, err = _client_or_error()
    if err:
        return err

    try:
        transitions = client.get_issue_transitions(issue_key)
        items = [
            {"id": str(t["id"]), "name": t["name"]}
            for t in transitions.get("transitions", transitions) if isinstance(t, dict)
        ]
        return {
            "status": "success",
            "issue_key": issue_key,
            "transitions": items,
        }
    except Exception as e:
        msg = f"Failed to get transitions for {issue_key}: {e}"
        logger.error(msg)
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": msg[:300]}


def transition_jira_issue(
    issue_key: str,
    status_name: str,
) -> Dict[str, Any]:
    """
    Move a Jira issue to a new status.

    Call get_issue_transitions first to find valid target status names.

    Args:
        issue_key: The issue key (e.g. "PROJ-123").
        status_name: The target status name (e.g. "In Progress", "Done").

    Returns:
        On success: {"status": "success", "issue_key": "...", "new_status": "..."}
        On failure: {"status": "error", "message": "..."}
    """
    client, err = _client_or_error()
    if err:
        return err

    try:
        result = client.set_issue_status(issue_key, status_name)
        logger.info("Transitioned %s to '%s'", issue_key, status_name)
        return {
            "status": "success",
            "issue_key": issue_key,
            "new_status": status_name,
        }
    except Exception as e:
        msg = f"Failed to transition {issue_key} to '{status_name}': {e}"
        logger.error(msg)
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": msg[:300]}


def add_jira_comment(
    issue_key: str,
    comment: str,
) -> Dict[str, Any]:
    """
    Add a text comment to a Jira issue.

    Args:
        issue_key: The issue key (e.g. "PROJ-123").
        comment: The comment text to add.

    Returns:
        On success: {"status": "success", "issue_key": "...", "comment_id": "..."}
        On failure: {"status": "error", "message": "..."}
    """
    client, err = _client_or_error()
    if err:
        return err

    try:
        result = client.issue_add_comment(issue_key, comment)
        comment_id = result.get("id", "unknown") if isinstance(result, dict) else str(result)
        logger.info("Added comment to %s", issue_key)
        return {
            "status": "success",
            "issue_key": issue_key,
            "comment_id": str(comment_id),
        }
    except Exception as e:
        msg = f"Failed to add comment to {issue_key}: {e}"
        logger.error(msg)
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": msg[:300]}


def search_jira_issues(
    jql: str,
    max_results: int = 20,
) -> Dict[str, Any]:
    """
    Search Jira issues using a JQL query.

    This is a power-user tool for arbitrary JQL. For common lookups prefer
    list_my_jira_issues.

    Args:
        jql: A JQL query string (e.g. 'project = PROJ AND status = "To Do"').
        max_results: Maximum number of results to return (default 20, max 50).

    Returns:
        On success: {"status": "success", "issues": [...], "total": N}
        On failure: {"status": "error", "message": "..."}
    """
    client, err = _client_or_error()
    if err:
        return err

    try:
        max_results = min(max(1, max_results), 50)
        result = client.jql(jql, limit=max_results)
        base_url = client.url

        issues = [_format_issue(i, base_url) for i in result.get("issues", [])]
        return {
            "status": "success",
            "issues": issues,
            "total": result.get("total", len(issues)),
        }
    except Exception as e:
        msg = f"Failed to search Jira issues: {e}"
        logger.error(msg)
        logger.debug(traceback.format_exc())
        return {"status": "error", "message": msg[:300]}


# ---------------------------------------------------------------------------
# Wrap as ADK FunctionTools
# ---------------------------------------------------------------------------

list_my_jira_issues_tool = FunctionTool(list_my_jira_issues)
get_jira_issue_tool = FunctionTool(get_jira_issue)
get_issue_transitions_tool = FunctionTool(get_issue_transitions)
transition_jira_issue_tool = FunctionTool(transition_jira_issue)
add_jira_comment_tool = FunctionTool(add_jira_comment)
search_jira_issues_tool = FunctionTool(search_jira_issues)

JIRA_TOOLS = [
    list_my_jira_issues_tool,
    get_jira_issue_tool,
    get_issue_transitions_tool,
    transition_jira_issue_tool,
    add_jira_comment_tool,
    search_jira_issues_tool,
]
