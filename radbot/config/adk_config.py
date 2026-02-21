"""
Configuration module for ADK to handle VertexAI settings from config.yaml.

This module provides functions to create a properly configured GenAI client.
"""

import inspect
import logging
import os
from typing import Any, Dict, Optional

import google.api_core.client_options as client_options
import google.auth

# ADK and GenAI imports
from google.genai.client import Client

from radbot.config.config_loader import config_loader

# Import our configuration
from radbot.config.settings import ConfigManager

# Configure logging
logger = logging.getLogger(__name__)

# Global configuration manager
config = ConfigManager()


def get_google_api_key() -> Optional[str]:
    """
    Get the Google API key from credential store, configuration, or environment variables.

    Returns:
        The API key or None if not found
    """
    # Try credential store first
    try:
        from radbot.credentials.store import get_credential_store

        store = get_credential_store()
        if store.available:
            api_key = store.get("google_api_key")
            if api_key:
                logger.info("Using Google API key from credential store")
                return api_key
    except Exception as e:
        logger.debug(f"Credential store lookup for google_api_key failed: {e}")

    # Check config.yaml
    api_key = config_loader.get_config().get("api_keys", {}).get("google")

    # If not found or empty, try environment variables
    if not api_key:
        # Try various environment variable names
        for env_var in ["GOOGLE_API_KEY", "GOOGLE_GENAI_API_KEY", "GEMINI_API_KEY"]:
            api_key = os.environ.get(env_var)
            if api_key:
                logger.info(f"Using Google API key from {env_var} environment variable")
                break

    return api_key


def create_client_with_config_settings() -> Client:
    """
    Create a genai Client initialized with settings from config.yaml.

    This handles both API key and Vertex AI authentication.

    Returns:
        Configured genai Client
    """
    # Check if using Vertex AI
    use_vertex_ai = config.is_using_vertex_ai()

    if use_vertex_ai:
        # Get Vertex AI settings from config
        project_id = config.get_vertex_project()
        location = config.get_vertex_location() or "us-central1"
        service_account_file = config_loader.get_agent_config().get(
            "service_account_file"
        )

        if not project_id:
            logger.error(
                "Vertex AI is enabled but project_id is missing in config.yaml"
            )
            raise ValueError("Missing Vertex AI project_id in configuration")

        logger.info(
            f"Initializing Vertex AI client for project {project_id} in {location}"
        )

        # Create client with Vertex AI settings
        try:
            # Set environment variables required by ADK for vertexai
            os.environ["GOOGLE_CLOUD_PROJECT"] = project_id

            # Set service account file if provided
            if service_account_file:
                if os.path.exists(service_account_file):
                    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = service_account_file
                    logger.info(f"Using service account file: {service_account_file}")
                else:
                    logger.warning(
                        f"Service account file not found: {service_account_file}"
                    )

            # Create the client with vertexai=True
            client = Client(vertexai=True, project=project_id, location=location)
            logger.info("Successfully created Vertex AI client")
            return client
        except Exception as e:
            logger.error(f"Failed to create Vertex AI client: {str(e)}")
            logger.warning("Falling back to API key authentication")
            use_vertex_ai = False

    # If not using Vertex AI or Vertex AI failed, use API key approach
    if not use_vertex_ai:
        api_key = get_google_api_key()

        if not api_key:
            logger.error(
                "No Google API key found in config.yaml or environment variables"
            )
            raise ValueError("Missing Google API key")

        logger.info("Initializing GenAI client with API key")

        # Create client with API key
        try:
            client = Client(api_key=api_key)
            logger.info("Successfully created GenAI client with API key")
            return client
        except Exception as e:
            logger.error(f"Failed to create GenAI client: {str(e)}")
            raise


def setup_vertex_environment():
    """
    Set up environment variables for Vertex AI or API key authentication.

    This function sets the necessary environment variables that ADK uses to
    determine whether to use Vertex AI and which project and location to use,
    or alternatively sets up API key-based authentication.

    Returns:
        True if using Vertex AI, False if using API key
    """
    # Reload config so we pick up DB overrides that arrived after import time
    config.reload_model_config()

    # Check if using Vertex AI
    use_vertex_ai = config.is_using_vertex_ai()

    if use_vertex_ai:
        # Get Vertex AI settings from config
        project_id = config.get_vertex_project()
        location = config.get_vertex_location() or "us-central1"
        service_account_file = config_loader.get_agent_config().get(
            "service_account_file"
        )

        if not project_id:
            logger.error(
                "Vertex AI is enabled but project_id is missing in config.yaml"
            )
            logger.warning("Falling back to API key authentication")
            use_vertex_ai = False
        else:
            logger.info(
                f"Setting up Vertex AI environment with project {project_id} in {location}"
            )

            # Set environment variables required by ADK for vertexai
            os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
            os.environ["GOOGLE_CLOUD_LOCATION"] = location
            os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"

            # Set service account file if provided
            if service_account_file:
                if os.path.exists(service_account_file):
                    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = service_account_file
                    logger.info(f"Using service account file: {service_account_file}")
                else:
                    logger.warning(
                        f"Service account file not found: {service_account_file}"
                    )

            return True

    # If not using Vertex AI or Vertex AI setup failed
    if not use_vertex_ai:
        # Make sure we don't accidentally use Vertex AI
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "FALSE"

        # Set up API key if available
        api_key = get_google_api_key()
        if api_key:
            # Set environment variable for API key that ADK will use
            os.environ["GOOGLE_API_KEY"] = api_key
            logger.info("Set up environment with Google API key")
        else:
            logger.warning("No Google API key found - ADK may fail to initialize")

        # Set project ID for quota attribution (Gmail, Calendar, etc.)
        project_id = config.get_google_cloud_project()
        if project_id:
            os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
            logger.info(f"Set GOOGLE_CLOUD_PROJECT={project_id} for quota attribution")

        return False


# Set up the environment when the module is imported
setup_vertex_environment()
