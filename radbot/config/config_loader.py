"""
ConfigLoader for YAML-based configuration with environment variable interpolation.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TypeVar, Union, cast

import yaml

# Try to import jsonschema for validation, but make it optional
try:
    import jsonschema

    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False

# Define logger
logger = logging.getLogger(__name__)

# Type variable for Python classes
T = TypeVar("T")


class ConfigError(Exception):
    """Exception raised for configuration errors."""

    pass


class ConfigLoader:
    """
    Loads and manages YAML configuration with environment variable interpolation.
    """

    def __init__(self, config_path: Optional[Union[str, Path]] = None):
        """
        Initialize the configuration loader.

        Args:
            config_path: Optional explicit path to config.yaml
        """
        self.env = os.getenv("RADBOT_ENV", "").strip().lower() or None
        self.config_path = self._find_config_path(config_path)
        self.schema_path = Path(__file__).parent / "schema" / "config_schema.json"
        self.config = self._load_config()
        env_label = self.env or "production"
        logger.info(f"ConfigLoader: env={env_label}, config={self.config_path}")

    def _find_config_path(self, config_path: Optional[Union[str, Path]] = None) -> Path:
        """
        Find the configuration file path.

        Looks in the following locations (in order):
        1. Explicit path provided to constructor
        2. Path specified by RADBOT_CONFIG / RADBOT_CONFIG_FILE environment variable
        3. Current working directory
        4. User's config directory (~/.config/radbot/)
        5. Project root directory

        When ``RADBOT_ENV`` is set (e.g. ``dev``), each directory is first checked
        for ``config.{env}.yaml`` before falling back to ``config.yaml``.

        Args:
            config_path: Optional explicit path to config.yaml

        Returns:
            Path to the configuration file

        Raises:
            ConfigError: If config.yaml cannot be found
        """
        # Check explicit path
        if config_path:
            path = Path(config_path)
            if path.exists():
                return path
            else:
                logger.warning(f"Specified config path does not exist: {path}")

        # Check environment variable (support both RADBOT_CONFIG and RADBOT_CONFIG_FILE)
        env_path = os.getenv("RADBOT_CONFIG") or os.getenv("RADBOT_CONFIG_FILE")
        if env_path:
            path = Path(env_path)
            if path.exists():
                return path
            else:
                logger.warning(
                    f"Config path from environment variable does not exist: {path}"
                )

        # Build candidate filenames: env-specific first, then generic
        candidates: List[str] = []
        if self.env:
            candidates.append(f"config.{self.env}.yaml")
        candidates.append("config.yaml")

        # Check current working directory
        for name in candidates:
            cwd_path = Path.cwd() / name
            if cwd_path.exists():
                return cwd_path

        # Check user's config directory
        user_config_dir = Path.home() / ".config" / "radbot"
        for name in candidates:
            user_config_path = user_config_dir / name
            if user_config_path.exists():
                return user_config_path

        # Check project root directory
        project_root = Path(__file__).parent.parent.parent
        for name in candidates:
            project_config_path = project_root / name
            if project_config_path.exists():
                return project_config_path

        # Check for example file to copy
        example_path = project_root / "examples" / "config.yaml.example"
        if example_path.exists():
            logger.warning(
                f"No config.yaml found. You can copy the example from {example_path} "
                f"to {project_root / 'config.yaml'} and customize it."
            )

        # If we reach here, we couldn't find config.yaml
        # Instead of raising an error, return a default path for potential creation
        logger.warning(
            f"No config.yaml found. Using default configuration with environment variables."
        )
        return project_root / "config.yaml"

    def _load_schema(self) -> Dict[str, Any]:
        """
        Load the JSON schema for validation.

        Returns:
            Dictionary containing the JSON schema
        """
        if not self.schema_path.exists():
            logger.warning(f"Schema file not found: {self.schema_path}")
            return {}

        try:
            with open(self.schema_path, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading schema: {e}")
            return {}

    def _interpolate_env_vars(self, value: Any) -> Any:
        """
        Recursively interpolate environment variables in configuration values.

        Replaces "${ENV_VAR}" or "$ENV_VAR" with the value of the environment variable.

        Args:
            value: The value to interpolate, can be a string, list, or dictionary

        Returns:
            The value with environment variables interpolated
        """
        if isinstance(value, str):
            # Match ${ENV_VAR} or $ENV_VAR
            pattern = r"\${([^}]+)}|\$([a-zA-Z0-9_]+)"

            def replace_env_var(match):
                env_var = match.group(1) or match.group(2)
                return os.environ.get(env_var, f"${{{env_var}}}")

            return re.sub(pattern, replace_env_var, value)
        elif isinstance(value, list):
            return [self._interpolate_env_vars(item) for item in value]
        elif isinstance(value, dict):
            return {k: self._interpolate_env_vars(v) for k, v in value.items()}
        else:
            return value

    def _validate_config(self, config: Dict[str, Any], schema: Dict[str, Any]) -> None:
        """
        Validate the configuration against the schema.

        Args:
            config: The configuration to validate
            schema: The JSON schema to validate against

        Raises:
            ConfigError: If validation fails
        """
        if not JSONSCHEMA_AVAILABLE:
            logger.warning(
                "jsonschema package not available. Skipping configuration validation."
            )
            return

        if not schema:
            logger.warning("No schema available. Skipping configuration validation.")
            return

        try:
            jsonschema.validate(instance=config, schema=schema)
        except jsonschema.exceptions.ValidationError as e:
            # Provide a more user-friendly error message
            path = " -> ".join([str(p) for p in e.path])
            message = f"Configuration validation error: {e.message}"
            if path:
                message = f"{message} (at {path})"
            raise ConfigError(message) from e

    def _load_config(self) -> Dict[str, Any]:
        """
        Load and validate the configuration file.

        Returns:
            Dictionary containing the configuration

        Raises:
            ConfigError: If the configuration file cannot be loaded or is invalid
        """
        # If the config file doesn't exist, return empty dict for fallback to env vars
        if not self.config_path.exists():
            logger.info(
                f"Configuration file not found: {self.config_path}. Using default configuration."
            )
            return self._get_default_config()

        try:
            with open(self.config_path, "r") as f:
                config = yaml.safe_load(f) or {}

            # Interpolate environment variables
            config = self._interpolate_env_vars(config)

            # Validate against schema
            schema = self._load_schema()
            self._validate_config(config, schema)

            return config
        except yaml.YAMLError as e:
            error_msg = f"Error parsing config.yaml: {e}"
            logger.error(error_msg)
            raise ConfigError(error_msg) from e
        except Exception as e:
            error_msg = f"Error loading configuration: {e}"
            logger.error(error_msg)
            raise ConfigError(error_msg) from e

    def _get_default_config(self) -> Dict[str, Any]:
        """
        Get a default configuration with hardcoded sensible defaults.

        All runtime configuration comes from the DB credential store
        (``config:<section>`` entries), managed via the Admin UI.  This method
        only provides baseline defaults for a fresh install before the admin
        has configured anything.

        Returns:
            Dictionary containing the default configuration
        """
        return {
            "agent": {
                "main_model": "gemini-2.5-pro",
                "sub_agent_model": "gemini-2.5-flash",
                "agent_models": {},
                "use_vertex_ai": False,
                "vertex_project": None,
                "vertex_location": "us-central1",
            },
            "cache": {
                "enabled": True,
                "ttl": 3600,
                "max_size": 1000,
                "selective": True,
                "min_tokens": 50,
                "redis_url": None,
            },
            "integrations": {
                "mcp": {"servers": []},
            },
        }

    def _deep_merge(
        self, base: Dict[str, Any], overlay: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Deep-merge *overlay* into *base* (overlay wins on leaf conflicts)."""
        merged = dict(base)
        for key, value in overlay.items():
            if (
                key in merged
                and isinstance(merged[key], dict)
                and isinstance(value, dict)
            ):
                merged[key] = self._deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged

    def load_db_config(self) -> None:
        """Load config overrides from the credential store and merge into self.config.

        Entries named ``config:<section>`` (e.g. ``config:agent``) are parsed as
        JSON and deep-merged on top of the file-based config.  The special key
        ``config:full`` replaces all non-database sections at once.

        This is a no-op when the credential store is unavailable.
        """
        try:
            from radbot.credentials.store import get_credential_store

            store = get_credential_store()
            if not store.available:
                return

            # Check for a full config blob first
            full_json = store.get("config:full")
            if full_json:
                import json as _json

                db_config = _json.loads(full_json)
                # Preserve the database section from file config (bootstrap)
                db_section = self.config.get("database")
                self.config = self._deep_merge(self.config, db_config)
                if db_section:
                    self.config["database"] = db_section
                logger.info("Loaded full config override from credential store")
                return

            # Otherwise merge individual sections
            import json as _json

            for entry in store.list():
                name = entry["name"]
                if not name.startswith("config:"):
                    continue
                section = name[len("config:") :]
                if section == "database":
                    continue  # never override DB bootstrap from the store
                raw = store.get(name)
                if raw:
                    try:
                        section_data = _json.loads(raw)
                        if section in self.config and isinstance(
                            self.config[section], dict
                        ):
                            self.config[section] = self._deep_merge(
                                self.config[section], section_data
                            )
                        else:
                            self.config[section] = section_data
                        logger.info(
                            f"Merged config section '{section}' from credential store"
                        )
                    except _json.JSONDecodeError:
                        logger.warning(
                            f"Invalid JSON in credential store key '{name}', skipping"
                        )
        except Exception as e:
            logger.debug(f"Could not load config from credential store: {e}")

    def get_config(self) -> Dict[str, Any]:
        """
        Get the full configuration.

        Returns:
            Dictionary containing the full configuration
        """
        return self.config

    def get_agent_config(self) -> Dict[str, Any]:
        """
        Get the agent configuration section.

        Returns:
            Dictionary containing the agent configuration
        """
        return self.config.get("agent", {})

    def get_cache_config(self) -> Dict[str, Any]:
        """
        Get the cache configuration section.

        Returns:
            Dictionary containing the cache configuration
        """
        return self.config.get("cache", {})

    def get_integrations_config(self) -> Dict[str, Any]:
        """
        Get the integrations configuration section.

        Returns:
            Dictionary containing the integrations configuration
        """
        return self.config.get("integrations", {})

    def get_home_assistant_config(self) -> Dict[str, Any]:
        """
        Get the Home Assistant configuration.

        Returns:
            Dictionary containing the Home Assistant configuration
        """
        integrations = self.get_integrations_config()
        return integrations.get("home_assistant", {})

    def get_mcp_config(self) -> Dict[str, Any]:
        """
        Get the MCP configuration.

        Returns:
            Dictionary containing the MCP configuration
        """
        integrations = self.get_integrations_config()
        return integrations.get("mcp", {})

    def get_mcp_servers(self) -> List[Dict[str, Any]]:
        """
        Get all configured MCP servers.

        Returns:
            List of MCP server configurations
        """
        mcp_config = self.get_mcp_config()
        return mcp_config.get("servers", [])

    def get_enabled_mcp_servers(self) -> List[Dict[str, Any]]:
        """
        Get only enabled MCP servers.

        Returns:
            List of enabled MCP server configurations
        """
        servers = self.get_mcp_servers()
        return [s for s in servers if s.get("enabled", True)]

    def get_mcp_server(self, server_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific MCP server by ID.

        Args:
            server_id: The ID of the MCP server

        Returns:
            Dictionary containing the MCP server configuration, or None if not found
        """
        servers = self.get_mcp_servers()
        for server in servers:
            if server.get("id") == server_id:
                return server
        return None

    def is_mcp_server_enabled(self, server_id: str) -> bool:
        """
        Check if a specific MCP server is enabled.

        Args:
            server_id: The ID of the MCP server

        Returns:
            Boolean indicating if the server is enabled
        """
        server = self.get_mcp_server(server_id)
        if server is None:
            return False
        return server.get("enabled", True)

    def get_logging_config(self) -> Dict[str, Any]:
        """
        Get the logging configuration.

        Returns:
            Dictionary containing the logging configuration
        """
        return self.config.get("logging", {})


# Create a singleton instance
config_loader = ConfigLoader()
