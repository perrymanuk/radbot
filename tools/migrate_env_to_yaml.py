#\!/usr/bin/env python3
"""
Migration script to convert .env file to config.yaml.

This script reads environment variables from a .env file and converts
them to a structured YAML format in config.yaml.
"""

import os
import re
import sys
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Set, List
from dotenv import dotenv_values

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Define sensitive variables that should use environment variable interpolation
SENSITIVE_VARS = {
    "HA_TOKEN", 
    "GOOGLE_API_KEY", 
    "GEMINI_API_KEY",
    "GOOGLE_GENAI_API_KEY",
    "REDIS_PASSWORD",
    "POSTGRES_PASSWORD",
    "DB_PASSWORD",
    "GOOGLE_APPLICATION_CREDENTIALS"  # Service account file path
}

# Mapping from environment variables to config.yaml paths
ENV_TO_CONFIG_MAP = {
    # Agent section
    "RADBOT_MAIN_MODEL": ["agent", "main_model"],
    "RADBOT_SUB_MODEL": ["agent", "sub_agent_model"],
    "GOOGLE_GENAI_USE_VERTEXAI": ["agent", "use_vertex_ai"],
    "GOOGLE_CLOUD_PROJECT": ["agent", "vertex_project"],
    "GOOGLE_CLOUD_LOCATION": ["agent", "vertex_location"],
    "GOOGLE_APPLICATION_CREDENTIALS": ["agent", "service_account_file"],
    
    # API keys section
    "GOOGLE_API_KEY": ["api_keys", "google"],
    "GEMINI_API_KEY": ["api_keys", "google"],
    "GOOGLE_GENAI_API_KEY": ["api_keys", "google"],
    
    # Cache section
    "RADBOT_CACHE_ENABLED": ["cache", "enabled"],
    "RADBOT_CACHE_TTL": ["cache", "ttl"],
    "RADBOT_CACHE_MAX_SIZE": ["cache", "max_size"],
    "RADBOT_CACHE_SELECTIVE": ["cache", "selective"],
    "RADBOT_CACHE_MIN_TOKENS": ["cache", "min_tokens"],
    "REDIS_URL": ["cache", "redis_url"],
    
    # Database section
    "POSTGRES_HOST": ["database", "host"],
    "POSTGRES_PORT": ["database", "port"],
    "POSTGRES_USER": ["database", "user"],
    "POSTGRES_PASSWORD": ["database", "password"],
    "POSTGRES_DB": ["database", "db_name"],
    "DB_API_PORT": ["database", "api_port"],
    
    # Vector DB section
    "QDRANT_URL": ["vector_db", "url"],
    "QDRANT_API_KEY": ["vector_db", "api_key"],
    "QDRANT_HOST": ["vector_db", "host"],
    "QDRANT_PORT": ["vector_db", "port"],
    "QDRANT_COLLECTION": ["vector_db", "collection"],
    
    # Home Assistant section
    "HA_URL": ["integrations", "home_assistant", "url"],
    "HA_TOKEN": ["integrations", "home_assistant", "token"],
    "HA_MCP_SSE_URL": ["integrations", "home_assistant", "mcp_sse_url"],
    
    # Calendar section
    "GOOGLE_CALENDAR_ID": ["integrations", "calendar", "calendar_id"],
    "GOOGLE_CALENDAR_SERVICE_ACCOUNT": ["integrations", "calendar", "service_account_file"],
    "CALENDAR_SERVICE_ACCOUNT_JSON": ["integrations", "calendar", "service_account_json"],
    "CALENDAR_TIMEZONE": ["integrations", "calendar", "timezone"],
    
    # Filesystem section
    "FS_ROOT_DIR": ["integrations", "filesystem", "root_dir"],
    "FS_ALLOW_WRITE": ["integrations", "filesystem", "allow_write"],
    "FS_ALLOW_DELETE": ["integrations", "filesystem", "allow_delete"],
    
    # Web UI section
    "WEB_PORT": ["web", "port"],
    "WEB_HOST": ["web", "host"],
    "WEB_DEBUG": ["web", "debug"],
    
    # Logging section
    "LOG_LEVEL": ["logging", "level"],
    "LOG_FORMAT": ["logging", "format"],
    "LOG_FILE": ["logging", "file"]
}

def nested_set(dic: Dict[str, Any], keys: List[str], value: Any) -> None:
    """
    Set a value in a nested dictionary.
    
    Args:
        dic: The dictionary to modify
        keys: List of nested keys
        value: The value to set
    """
    for key in keys[:-1]:
        dic = dic.setdefault(key, {})
    
    # Convert boolean values
    if isinstance(value, str) and value.upper() in ("TRUE", "YES", "1"):
        dic[keys[-1]] = True
    elif isinstance(value, str) and value.upper() in ("FALSE", "NO", "0"):
        dic[keys[-1]] = False
    # Convert numeric values
    elif isinstance(value, str) and value.isdigit():
        dic[keys[-1]] = int(value)
    elif isinstance(value, str) and re.match(r'^-?\d+(\.\d+)?$', value):
        dic[keys[-1]] = float(value)
    # Keep as string
    else:
        dic[keys[-1]] = value

def get_config_value(env_var: str, value: str, sensitive_vars: Set[str]) -> Any:
    """
    Get the appropriate config value, handling sensitive data.
    
    Args:
        env_var: The environment variable name
        value: The value from the .env file
        sensitive_vars: Set of sensitive environment variables
        
    Returns:
        The processed value for config.yaml
    """
    # For sensitive data, use environment variable interpolation
    if env_var in sensitive_vars and value:
        return f"${{{env_var}}}"
    
    # Handle boolean values
    if value.upper() in ("TRUE", "YES", "1"):
        return True
    elif value.upper() in ("FALSE", "NO", "0"):
        return False
    
    # Handle numeric values
    if value.isdigit():
        return int(value)
    elif re.match(r'^-?\d+(\.\d+)?$', value):
        return float(value)
    
    # Return as string otherwise
    return value

def convert_env_to_yaml(env_path: str, yaml_path: str, sensitive_vars: Set[str] = None) -> bool:
    """
    Convert an .env file to config.yaml.
    
    Args:
        env_path: Path to the .env file
        yaml_path: Path where the YAML file will be written
        sensitive_vars: Set of sensitive environment variables
        
    Returns:
        True if successful, False otherwise
    """
    if sensitive_vars is None:
        sensitive_vars = SENSITIVE_VARS
    
    # Check if .env file exists
    env_path = Path(env_path)
    if not env_path.exists():
        logger.error(f".env file not found: {env_path}")
        return False
    
    # Check if yaml_path already exists
    yaml_path = Path(yaml_path)
    if yaml_path.exists():
        logger.warning(f"config.yaml already exists: {yaml_path}")
        user_input = input("Do you want to overwrite it? (y/n): ")
        if user_input.lower() \!= 'y':
            logger.info("Migration cancelled by user")
            return False
    
    try:
        # Load environment variables from .env file
        logger.info(f"Loading environment variables from {env_path}")
        env_vars = dotenv_values(env_path)
        
        # Create config structure
        config = {}
        
        # Process each environment variable
        for env_var, value in env_vars.items():
            if not value or value.strip() == '':
                logger.debug(f"Skipping empty value for {env_var}")
                continue
                
            # Check if we have a mapping for this variable
            if env_var in ENV_TO_CONFIG_MAP:
                keys = ENV_TO_CONFIG_MAP[env_var]
                processed_value = get_config_value(env_var, value, sensitive_vars)
                nested_set(config, keys, processed_value)
            else:
                logger.warning(f"No mapping found for environment variable: {env_var}")
        
        # Add enabled flags for integrations
        add_integration_enabled_flags(config)
        
        # Write YAML file
        with open(yaml_path, 'w') as f:
            # Add header comments
            f.write("# Radbot Configuration\n")
            f.write("# Generated by migrate_env_to_yaml.py\n")
            f.write(f"# Original .env file: {env_path.name}\n")
            f.write("#\n")
            f.write("# For more information and examples, see:\n")
            f.write("# docs/implementation/yaml_config_mcp_integration.md\n\n")
            
            # Dump configuration with proper formatting
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        
        logger.info(f"Successfully created config.yaml at {yaml_path}")
        logger.info(f"Please check the file and update any missing values")
        return True
        
    except Exception as e:
        logger.error(f"Error converting .env to config.yaml: {e}")
        return False

def add_integration_enabled_flags(config: Dict[str, Any]) -> None:
    """
    Add enabled flags for integrations based on whether
    required configuration is present.
    
    Args:
        config: The configuration dictionary to modify
    """
    integrations = config.get("integrations", {})
    
    # Home Assistant
    ha_config = integrations.get("home_assistant", {})
    ha_url = ha_config.get("url")
    ha_token = ha_config.get("token")
    if ha_url and ha_token:
        ha_config["enabled"] = True
    else:
        ha_config["enabled"] = False
    
    # Calendar
    calendar_config = integrations.get("calendar", {})
    calendar_id = calendar_config.get("calendar_id")
    service_account = calendar_config.get("service_account_file") or calendar_config.get("service_account_json")
    if calendar_id and service_account:
        calendar_config["enabled"] = True
    else:
        calendar_config["enabled"] = False
    
def main() -> int:
    """
    Main function to convert .env to config.yaml.
    
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    # Get paths
    project_root = Path(__file__).parent.parent
    env_path = project_root / ".env"
    yaml_path = project_root / "config.yaml"
    
    print(f"Converting {env_path} to {yaml_path}")
    
    # Ask for confirmation
    user_input = input("Do you want to proceed? (y/n): ")
    if user_input.lower() \!= 'y':
        print("Migration cancelled by user")
        return 0
    
    # Convert .env to config.yaml
    success = convert_env_to_yaml(env_path, yaml_path)
    
    if success:
        print("\nMigration completed successfully\!")
        print(f"Please check the generated file at: {yaml_path}")
        print("\nNext steps:")
        print("1. Review the generated config.yaml file")
        print("2. Update any missing or incorrect values")
        print("3. Test the configuration with test_yaml_integrations.py")
        print("4. Make a backup of your .env file if needed")
        return 0
    else:
        print("\nMigration failed. Please check the logs for details.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
EOF < /dev/null