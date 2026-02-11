"""
Configuration module for ADK to handle VertexAI and API key settings.

All runtime configuration comes from the DB credential store (managed
via the Admin UI).  Only ``database``, ``credential_key``, and
``admin_token`` live in ``config.yaml``.
"""

import logging
import os
from typing import Optional

from google.genai.client import Client

from radbot.config.config_loader import config_loader
from radbot.config.settings import ConfigManager

logger = logging.getLogger(__name__)

# Module-level ConfigManager — reload_model_config() is called in
# setup_vertex_environment() so it always reflects current DB state.
config = ConfigManager()


def get_google_api_key() -> Optional[str]:
    """Get the Google API key from the credential store or DB config.

    Returns:
        The API key or None if not found
    """
    # Credential store (encrypted)
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

    # Fall back to api_keys.google in merged config (file + DB)
    api_key = config_loader.get_config().get("api_keys", {}).get("google")
    return api_key


def create_client_with_config_settings() -> Client:
    """Create a genai Client using DB-managed configuration.

    Returns:
        Configured genai Client
    """
    config.reload_model_config()
    use_vertex_ai = config.is_using_vertex_ai()

    if use_vertex_ai:
        project_id = config.get_vertex_project()
        location = config.get_vertex_location() or "us-central1"
        service_account_file = config_loader.get_agent_config().get(
            "service_account_file"
        )

        if not project_id:
            logger.error("Vertex AI is enabled but project_id is missing")
            raise ValueError("Missing Vertex AI project_id in configuration")

        logger.info(
            f"Initializing Vertex AI client for project {project_id} in {location}"
        )

        try:
            os.environ["GOOGLE_CLOUD_PROJECT"] = project_id

            if service_account_file and os.path.exists(service_account_file):
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = service_account_file
                logger.info(f"Using service account file: {service_account_file}")

            client = Client(vertexai=True, project=project_id, location=location)
            logger.info("Successfully created Vertex AI client")
            return client
        except Exception as e:
            logger.error(f"Failed to create Vertex AI client: {e}")
            logger.warning("Falling back to API key authentication")

    # API key path
    api_key = get_google_api_key()
    if not api_key:
        logger.error("No Google API key found in credential store or config")
        raise ValueError("Missing Google API key")

    logger.info("Initializing GenAI client with API key")
    client = Client(api_key=api_key)
    logger.info("Successfully created GenAI client with API key")
    return client


def setup_vertex_environment():
    """Set up ADK environment variables from DB config.

    Sets ``GOOGLE_GENAI_USE_VERTEXAI`` and related env vars that ADK's
    internal google-genai SDK reads.  Called at import time and again
    during app startup after DB config is loaded.

    Returns:
        True if using Vertex AI, False if using API key
    """
    # Always reload so we reflect the latest DB state
    config.reload_model_config()

    use_vertex_ai = config.is_using_vertex_ai()

    if use_vertex_ai:
        project_id = config.get_vertex_project()
        location = config.get_vertex_location() or "us-central1"
        service_account_file = config_loader.get_agent_config().get(
            "service_account_file"
        )

        if not project_id:
            logger.error("Vertex AI enabled but project_id missing — falling back to API key")
            use_vertex_ai = False
        else:
            logger.info(
                f"Setting up Vertex AI environment: project={project_id}, location={location}"
            )
            os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
            os.environ["GOOGLE_CLOUD_LOCATION"] = location
            os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"

            if service_account_file and os.path.exists(service_account_file):
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = service_account_file
                logger.info(f"Using service account file: {service_account_file}")

            return True

    # Not using Vertex AI — ensure the env var is cleared
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "FALSE"

    api_key = get_google_api_key()
    if api_key:
        os.environ["GOOGLE_API_KEY"] = api_key
        logger.info("Set up environment with Google API key")
    else:
        logger.info("No Google API key found yet (will retry after DB config loads)")

    return False


# Set up the environment when the module is imported
setup_vertex_environment()
