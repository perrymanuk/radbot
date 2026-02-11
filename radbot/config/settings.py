"""
Configuration settings and management for the radbot agent framework.

All runtime configuration comes from the DB credential store (managed via
the Admin UI).  Only ``database``, ``credential_key``, and ``admin_token``
live in ``config.yaml``.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Import the YAML/DB config loader
from radbot.config.config_loader import config_loader

# Default paths
DEFAULT_CONFIG_DIR = Path(__file__).parent / "default_configs"


class ConfigManager:
    """
    Manager for agent configuration settings.

    Handles loading instruction prompts, model selection, and other configuration settings.
    """

    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize the configuration manager.

        Args:
            config_dir: Optional directory path for configuration files
        """
        self.config_dir = config_dir or DEFAULT_CONFIG_DIR
        self.model_config = self._load_model_config()
        self.ha_config = self._load_home_assistant_config()
        self.instruction_cache = {}

    def _load_model_config(self) -> Dict[str, Any]:
        """
        Load model configuration from the DB-merged config (via config_loader).

        All runtime configuration is stored in the DB credential store and
        managed through the Admin UI.  Hardcoded defaults are used only when
        the DB has no value yet (fresh install).

        Returns:
            Dictionary of model configuration settings
        """
        agent_config = config_loader.get_agent_config()

        return {
            "main_model": agent_config.get("main_model") or "gemini-2.5-pro",
            "sub_agent_model": agent_config.get("sub_agent_model") or "gemini-2.5-flash",
            "agent_models": agent_config.get("agent_models", {}),
            "use_vertex_ai": bool(agent_config.get("use_vertex_ai", False)),
            "vertex_project": agent_config.get("vertex_project"),
            "vertex_location": agent_config.get("vertex_location", "us-central1"),
            "service_account_file": agent_config.get("service_account_file"),
            "enable_adk_search": bool(agent_config.get("enable_adk_search", False)),
            "enable_adk_code_execution": bool(agent_config.get("enable_adk_code_execution", False)),
        }

    def reload_model_config(self) -> None:
        """Re-read model configuration from config_loader (after DB config changes)."""
        self.model_config = self._load_model_config()

    def _get_ollama_config(self) -> dict:
        """Fetch Ollama settings from DB config and credential store.

        Returns dict with keys: api_base, api_key, enabled.
        """
        try:
            cfg = config_loader.get_integrations_config().get("ollama", {})
        except Exception:
            cfg = {}

        api_base = cfg.get("api_base")
        api_key = cfg.get("api_key")
        enabled = cfg.get("enabled", True)

        if not api_key:
            try:
                from radbot.credentials.store import get_credential_store

                store = get_credential_store()
                if store.available:
                    api_key = store.get("ollama_api_key")
            except Exception:
                pass

        return {"api_base": api_base, "api_key": api_key, "enabled": enabled}

    def resolve_model(self, model_string: str) -> Union[str, Any]:
        """Resolve a model string, wrapping Ollama models in LiteLlm.

        If *model_string* starts with ``ollama_chat/`` or ``ollama/``, returns
        a :class:`google.adk.models.lite_llm.LiteLlm` instance configured with
        the Ollama ``api_base``.  Otherwise the string is returned unchanged
        (the Gemini path).
        """
        if not model_string:
            return model_string

        if model_string.startswith("ollama_chat/") or model_string.startswith("ollama/"):
            from google.adk.models.lite_llm import LiteLlm

            ollama_cfg = self._get_ollama_config()
            kwargs: Dict[str, Any] = {}
            if ollama_cfg.get("api_base"):
                kwargs["api_base"] = ollama_cfg["api_base"]
                # Set env var as fallback so litellm can always find Ollama
                os.environ["OLLAMA_API_BASE"] = ollama_cfg["api_base"]
            if ollama_cfg.get("api_key"):
                kwargs["api_key"] = ollama_cfg["api_key"]

            # Ensure Vertex AI is disabled when using Ollama models —
            # the env var would cause ADK/google-genai to route Gemini
            # sub-agent calls through Vertex, which may not be configured.
            os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "FALSE"

            # Ensure GOOGLE_API_KEY is set for sub-agents that still use Gemini
            # (search_agent, code_execution_agent always require Gemini).
            if not os.environ.get("GOOGLE_API_KEY"):
                try:
                    from radbot.config.adk_config import get_google_api_key

                    api_key = get_google_api_key()
                    if api_key:
                        os.environ["GOOGLE_API_KEY"] = api_key
                except Exception:
                    pass

            _logger = logging.getLogger(__name__)
            _logger.info(
                "Resolved Ollama model '%s' (api_base=%s)",
                model_string,
                kwargs.get("api_base", "<default>"),
            )
            return LiteLlm(model=model_string, **kwargs)

        return model_string

    @staticmethod
    def _model_name(model: Any) -> str:
        """Extract a printable model name from either a string or LiteLlm object."""
        if isinstance(model, str):
            return model
        # LiteLlm stores its model name in .model
        return getattr(model, "model", str(model))

    def apply_model_config(self, root_agent) -> None:
        """Reload model config and apply to root_agent and its sub-agents.

        This is the single place where model changes are pushed onto the
        live agent tree.  Called from web startup, CLI startup, and admin
        hot-reload.
        """
        _logger = logging.getLogger(__name__)
        self.reload_model_config()

        new_model_str = self.get_main_model()
        old_name = self._model_name(root_agent.model)
        if old_name != new_model_str:
            root_agent.model = self.resolve_model(new_model_str)
            _logger.info(f"Applied model config: {old_name} -> {new_model_str}")

        for sa in root_agent.sub_agents or []:
            name = getattr(sa, "name", None)
            if not name:
                continue
            lookup = name if name.endswith("_agent") else f"{name}_agent"
            new_sa_model_str = self.get_agent_model(lookup)
            old_sa_name = self._model_name(sa.model)
            if old_sa_name != new_sa_model_str:
                _logger.info(
                    f"Applied sub-agent '{name}' model: {old_sa_name} -> {new_sa_model_str}"
                )
                sa.model = self.resolve_model(new_sa_model_str)

    def _load_home_assistant_config(self) -> Dict[str, Any]:
        """
        Load Home Assistant configuration from DB config.

        Returns:
            Dictionary of Home Assistant configuration settings
        """
        ha_config = config_loader.get_home_assistant_config()

        ha_url = ha_config.get("url")
        ha_token = ha_config.get("token")
        ha_mcp_sse_url = ha_config.get("mcp_sse_url")
        ha_enabled = ha_config.get("enabled", bool(ha_url and ha_token))

        return {
            "use_rest_api": True,
            "enabled": ha_enabled,
            "url": ha_url,
            "token": ha_token,
            "mcp_sse_url": ha_mcp_sse_url,
        }

    def get_instruction(self, name: str) -> str:
        """
        Get an instruction prompt by name.

        Args:
            name: Name of the instruction prompt to load

        Returns:
            The instruction prompt text

        Raises:
            FileNotFoundError: If the instruction file doesn't exist
        """
        # Return from cache if already loaded
        if name in self.instruction_cache:
            return self.instruction_cache[name]

        # Load the instruction from file
        instruction_path = self.config_dir / "instructions" / f"{name}.md"
        if not instruction_path.exists():
            raise FileNotFoundError(
                f"Instruction prompt '{name}' not found at {instruction_path}"
            )

        # Read, cache, and return the instruction
        instruction = instruction_path.read_text(encoding="utf-8")
        self.instruction_cache[name] = instruction
        return instruction

    def get_schema_config(self, schema_name: str) -> Dict[str, Any]:
        """
        Get JSON schema configuration for structured data interfaces.

        Args:
            schema_name: Name of the schema to load

        Returns:
            Dictionary representation of the JSON schema

        Raises:
            FileNotFoundError: If the schema file doesn't exist
        """
        schema_path = self.config_dir / "schemas" / f"{schema_name}.json"
        if not schema_path.exists():
            raise FileNotFoundError(
                f"Schema '{schema_name}' not found at {schema_path}"
            )

        with open(schema_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_main_model(self) -> str:
        """
        Get the main agent model name from DB config.

        Returns:
            The configured main model name
        """
        return self.model_config["main_model"] or "gemini-2.5-pro"

    def get_sub_agent_model(self) -> str:
        """
        Get the sub-agent model name.

        Returns:
            The configured sub-agent model name
        """
        return self.model_config["sub_agent_model"]

    def get_agent_model(self, agent_name: str) -> str:
        """
        Get the model for a specific agent type.

        Args:
            agent_name: The name of the agent (e.g., "code_execution_agent", "search_agent")

        Returns:
            The configured model for the specified agent, or the default sub-agent model if not configured
        """
        agent_models = self.model_config.get("agent_models", {})

        # Return the agent-specific model if configured, otherwise fall back to appropriate default
        if agent_name in agent_models and agent_models[agent_name]:
            return agent_models[agent_name]

        # For scout (research) agent, use main model by default since it's complex
        if agent_name == "scout_agent":
            return self.get_main_model()

        # For specialized search and code execution agents, use main model too
        if agent_name in ["search_agent", "code_execution_agent"]:
            return self.get_main_model()

        # For all other agents, use the general sub_agent_model
        return self.get_sub_agent_model()

    def is_using_vertex_ai(self) -> bool:
        """
        Check if the agent is configured to use Vertex AI.

        Returns:
            True if using Vertex AI, False otherwise
        """
        return self.model_config["use_vertex_ai"]

    def get_vertex_project(self) -> Optional[str]:
        """
        Get the Google Cloud project ID for Vertex AI.

        Returns:
            The project ID or None if not configured
        """
        return self.model_config.get("vertex_project")

    def get_vertex_location(self) -> str:
        """
        Get the Google Cloud location for Vertex AI.

        Returns:
            The location (defaults to "us-central1" if not configured)
        """
        return self.model_config.get("vertex_location", "us-central1")

    def get_service_account_file(self) -> Optional[str]:
        """
        Get the Google Cloud service account file path for Vertex AI.

        Returns:
            The service account file path or None if not configured
        """
        return self.model_config.get("service_account_file")

    def is_adk_search_enabled(self) -> bool:
        """
        Check if the ADK Google Search built-in tool is enabled.

        Returns:
            True if ADK Google Search is enabled, False otherwise
        """
        return self.model_config.get("enable_adk_search", False)

    def is_adk_code_execution_enabled(self) -> bool:
        """
        Check if the ADK Code Execution built-in tool is enabled.

        Returns:
            True if ADK Code Execution is enabled, False otherwise
        """
        return self.model_config.get("enable_adk_code_execution", False)

    def get_home_assistant_config(self) -> Dict[str, Any]:
        """
        Get the Home Assistant configuration settings.

        Returns:
            Dictionary with Home Assistant configuration
        """
        return self.ha_config

    def is_home_assistant_enabled(self) -> bool:
        """
        Check if Home Assistant integration is enabled and properly configured.

        Returns:
            True if Home Assistant integration is enabled, False otherwise
        """
        return self.ha_config.get("enabled", False)

    def get_home_assistant_url(self) -> Optional[str]:
        """
        Get the Home Assistant URL.

        Returns:
            The Home Assistant URL or None if not configured
        """
        return self.ha_config.get("url")

    def get_home_assistant_token(self) -> Optional[str]:
        """
        Get the Home Assistant authentication token.

        Returns:
            The Home Assistant token or None if not configured
        """
        return self.ha_config.get("token")
