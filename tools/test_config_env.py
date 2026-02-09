#!/usr/bin/env python3
"""
Test script to check if environment variables are properly set from config.yaml.
"""

import os
import sys
import logging
from pathlib import Path

# Add parent directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from radbot.config.config_loader import config_loader
from radbot.config.settings import ConfigManager
from radbot.config.adk_config import setup_vertex_environment

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Check environment variables setup from config.yaml."""
    print("Configuration Environment Test")
    print("=============================")
    
    # Get the agent configuration
    agent_config = config_loader.get_agent_config()
    
    # Print the basic configuration
    print("\nConfiguration from config.yaml:")
    for key, value in agent_config.items():
        print(f"  {key}: {value}")
    
    # Also print API keys configuration
    api_keys_config = config_loader.get_config().get("api_keys", {})
    print("\nAPI Keys configuration:")
    for key, value in api_keys_config.items():
        if key == "google" and value:
            print(f"  {key}: ****")
        else:
            print(f"  {key}: {value}")
    
    # Print the actual environment variables
    print("\nInitial environment variables:")
    for var in ["GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION", "GOOGLE_API_KEY"]:
        value = os.environ.get(var)
        if var == "GOOGLE_API_KEY" and value:
            print(f"  {var}: ****")
        else:
            print(f"  {var}: {value}")
    
    # Check if Vertex AI is enabled and set up the environment again
    result = setup_vertex_environment()
    print(f"\nsetup_vertex_environment() result: {result}")
    
    # Print environment variables again to confirm they're set
    print("\nEnvironment variables after setup:")
    for var in ["GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION", "GOOGLE_API_KEY"]:
        value = os.environ.get(var)
        if var == "GOOGLE_API_KEY" and value:
            print(f"  {var}: ****")
        else:
            print(f"  {var}: {value}")
    
    # Test which authentication method is being used
    use_vertex_ai = result  # Same as os.environ.get("GOOGLE_GENAI_USE_VERTEXAI") == "TRUE"
    if use_vertex_ai:
        print("\nUsing Vertex AI authentication:")
        print(f"  Project: {os.environ.get('GOOGLE_CLOUD_PROJECT')}")
        print(f"  Location: {os.environ.get('GOOGLE_CLOUD_LOCATION')}")
    else:
        api_key = os.environ.get("GOOGLE_API_KEY")
        if api_key:
            print("\nUsing API key authentication")
        else:
            print("\nWARNING: No authentication method configured!")
    
    print("\nConfiguration test completed successfully.")
    return 0

if __name__ == "__main__":
    sys.exit(main())