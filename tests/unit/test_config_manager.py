"""
Unit tests for the ConfigManager class.
"""

import json
import os
from pathlib import Path
from unittest.mock import mock_open, patch

import pytest

from radbot.config.settings import ConfigManager


# Test fixture for a temporary config directory
@pytest.fixture
def temp_config_dir(tmp_path):
    """Create a temporary config directory structure for testing."""
    # Create directory structure
    instructions_dir = tmp_path / "instructions"
    schemas_dir = tmp_path / "schemas"
    instructions_dir.mkdir()
    schemas_dir.mkdir()

    # Create test instruction file
    test_instruction = (
        "# Test Instruction\nThis is a test instruction for unit testing."
    )
    (instructions_dir / "test.md").write_text(test_instruction)

    # Create test schema file
    test_schema = {"title": "TestSchema", "type": "object", "properties": {}}
    with open(schemas_dir / "test.json", "w") as f:
        json.dump(test_schema, f)

    return tmp_path


def test_init_default_config_dir():
    """Test that ConfigManager initializes with the default config directory."""
    config = ConfigManager()
    assert config.config_dir == Path(config.config_dir)
    assert "default_configs" in str(config.config_dir)


def test_init_custom_config_dir(temp_config_dir):
    """Test that ConfigManager initializes with a custom config directory."""
    config = ConfigManager(config_dir=temp_config_dir)
    assert config.config_dir == temp_config_dir


def test_load_model_config():
    """Test that model configuration is loaded correctly."""
    # Test with default values
    config = ConfigManager()
    model_config = config._load_model_config()
    assert "main_model" in model_config
    assert "sub_agent_model" in model_config
    assert "use_vertex_ai" in model_config

    # Test with environment variables
    with patch.dict(
        os.environ,
        {
            "RADBOT_MAIN_MODEL": "test-model",
            "RADBOT_SUB_MODEL": "test-sub-model",
            "GOOGLE_GENAI_USE_VERTEXAI": "TRUE",
        },
    ):
        config = ConfigManager()
        model_config = config._load_model_config()
        assert model_config["main_model"] == "test-model"
        assert model_config["sub_agent_model"] == "test-sub-model"
        assert model_config["use_vertex_ai"] is True


def test_get_instruction(temp_config_dir):
    """Test retrieving an instruction from the file system."""
    config = ConfigManager(config_dir=temp_config_dir)
    instruction = config.get_instruction("test")
    assert "Test Instruction" in instruction
    assert "This is a test instruction for unit testing." in instruction

    # Test caching
    assert "test" in config.instruction_cache
    assert config.instruction_cache["test"] == instruction

    # Test handling of missing instruction
    with pytest.raises(FileNotFoundError):
        config.get_instruction("nonexistent")


def test_get_schema_config(temp_config_dir):
    """Test retrieving a schema configuration from the file system."""
    config = ConfigManager(config_dir=temp_config_dir)
    schema = config.get_schema_config("test")
    assert schema["title"] == "TestSchema"
    assert schema["type"] == "object"

    # Test handling of missing schema
    with pytest.raises(FileNotFoundError):
        config.get_schema_config("nonexistent")


def test_get_main_model():
    """Test retrieving the main model name."""
    with patch.dict(os.environ, {"RADBOT_MAIN_MODEL": "custom-model"}):
        config = ConfigManager()
        assert config.get_main_model() == "custom-model"


def test_get_sub_agent_model():
    """Test retrieving the sub-agent model name."""
    with patch.dict(os.environ, {"RADBOT_SUB_MODEL": "custom-sub-model"}):
        config = ConfigManager()
        assert config.get_sub_agent_model() == "custom-sub-model"


def test_is_using_vertex_ai():
    """Test checking if Vertex AI is being used."""
    # Test when Vertex AI is enabled
    with patch.dict(os.environ, {"GOOGLE_GENAI_USE_VERTEXAI": "TRUE"}):
        config = ConfigManager()
        assert config.is_using_vertex_ai() is True

    # Test when Vertex AI is disabled
    with patch.dict(os.environ, {"GOOGLE_GENAI_USE_VERTEXAI": "FALSE"}):
        config = ConfigManager()
        assert config.is_using_vertex_ai() is False

    # Test default when environment variable is not set
    with patch.dict(os.environ, {}, clear=True):
        config = ConfigManager()
        assert config.is_using_vertex_ai() is False
