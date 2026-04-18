"""
Agent info API endpoint for RadBot web interface.

This module provides API endpoints for retrieving agent and model information,
as well as Claude templates from the configuration.
"""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter

from radbot.config import config_manager, get_claude_templates

logger = logging.getLogger(__name__)

# Create routers
router = APIRouter(
    prefix="/api/agent-info",
    tags=["agent-info"],
)

claude_router = APIRouter(
    prefix="/api/claude-templates",
    tags=["claude-templates"],
)


# Sub-agents that require Gemini (cannot use Ollama/LiteLLM routes):
#   - search_agent uses google_search grounding
#   - code_execution_agent uses BuiltInCodeExecutor
# See CLAUDE.md "Known Gotchas".
_GEMINI_ONLY = {"search_agent", "code_execution_agent"}


def _agent_config_key(name: str) -> str:
    """Normalise a runtime agent name → canonical config key.

    Runtime agents from ``root_agent.sub_agents`` use names like ``casa`` or
    ``scout``. Config keys in ``config:agent.agent_models`` use ``<name>_agent``
    (e.g. ``casa_agent``). Agents already named ``*_agent`` (``search_agent``,
    ``code_execution_agent``) are kept as-is.
    """
    lower = name.lower()
    if lower.endswith("_agent"):
        return lower
    return f"{lower}_agent"


def _enumerate_sub_agents() -> List[Dict[str, Any]]:
    """Return the list of runtime sub-agents, each with its resolved model.

    Sources the roster from ``root_agent.sub_agents`` so new agents show up
    automatically without frontend edits.
    """
    try:
        from agent import root_agent  # root-level re-export
    except Exception as e:
        logger.warning("Could not import root_agent for sub-agent enumeration: %s", e)
        return []

    sub_agents = getattr(root_agent, "sub_agents", None) or []
    out: List[Dict[str, Any]] = []
    for sa in sub_agents:
        name = getattr(sa, "name", None)
        if not name:
            continue
        key = _agent_config_key(name)
        try:
            resolved = config_manager.get_agent_model(key)
        except Exception:
            resolved = ""
        out.append(
            {
                "name": name,
                "config_key": key,
                "resolved_model": resolved,
                "gemini_only": key in _GEMINI_ONLY,
            }
        )
    return out


@router.get("")
async def get_agent_info() -> Dict[str, Any]:
    """Get information about the current agent and models.

    Returns:
        Dict containing:
          - ``agent_name``: main agent display name
          - ``model``: main agent's resolved model
          - ``sub_agents``: list of sub-agent names (backwards-compat)
          - ``sub_agents_detail``: [{name, config_key, resolved_model, gemini_only}]
          - ``agent_models``: resolved model per sub-agent (canonical config keys)
    """
    main_model = config_manager.get_main_model()
    sub_agents_detail = _enumerate_sub_agents()

    # Build agent_models dynamically from runtime roster.
    agent_models: Dict[str, str] = {"beto": main_model}
    for sa in sub_agents_detail:
        agent_models[sa["config_key"]] = sa["resolved_model"]

    sub_agent_names = [sa["name"] for sa in sub_agents_detail]

    info = {
        "name": "BETO",
        "agent_name": "BETO",  # legacy key
        "model": main_model,
        "sub_agents": sub_agent_names,
        "sub_agents_detail": sub_agents_detail,
        "agent_models": agent_models,
    }

    logger.debug("Providing agent info: %s", info)
    return info


@claude_router.get("")
async def get_claude_templates_route() -> Dict[str, Any]:
    """Get Claude templates from configuration."""
    claude_templates = get_claude_templates()
    logger.debug("Providing Claude templates: %s", list(claude_templates.keys()))
    return {"templates": claude_templates}


def register_agent_info_router(app):
    """Register agent_info and claude_templates routers with the FastAPI app."""
    app.include_router(router)
    app.include_router(claude_router)
    logger.debug("Registered agent_info and claude_templates routers")
