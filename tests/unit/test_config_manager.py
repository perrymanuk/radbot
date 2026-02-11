"""
Unit tests for the ConfigManager class.

All runtime config comes from the DB credential store (via config_loader).
These tests verify defaults and DB-loaded values — env vars are NOT a
config source (only database, credential_key, admin_token in config.yaml).
"""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from radbot.config.settings import ConfigManager


# Test fixture for a temporary config directory
@pytest.fixture
def temp_config_dir(tmp_path):
    """Create a temporary config directory structure for testing."""
    instructions_dir = tmp_path / "instructions"
    schemas_dir = tmp_path / "schemas"
    instructions_dir.mkdir()
    schemas_dir.mkdir()

    test_instruction = (
        "# Test Instruction\nThis is a test instruction for unit testing."
    )
    (instructions_dir / "test.md").write_text(test_instruction)

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
    """Test that model configuration is loaded from DB config with defaults."""
    config = ConfigManager()
    model_config = config._load_model_config()
    assert "main_model" in model_config
    assert "sub_agent_model" in model_config
    assert "use_vertex_ai" in model_config
    # Defaults when no DB config is set
    assert model_config["use_vertex_ai"] is False
    assert isinstance(model_config["agent_models"], dict)


def test_load_model_config_from_db():
    """Test that model configuration is loaded from config_loader (DB)."""
    from radbot.config.config_loader import config_loader

    # Simulate DB config by patching the agent config
    db_agent_config = {
        "main_model": "ollama_chat/test-model",
        "sub_agent_model": "ollama_chat/test-sub",
        "use_vertex_ai": True,
        "vertex_project": "my-project",
    }
    with patch.object(config_loader, "get_agent_config", return_value=db_agent_config):
        config = ConfigManager()
        model_config = config._load_model_config()
        assert model_config["main_model"] == "ollama_chat/test-model"
        assert model_config["sub_agent_model"] == "ollama_chat/test-sub"
        assert model_config["use_vertex_ai"] is True
        assert model_config["vertex_project"] == "my-project"


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
    """Test retrieving the main model name (from DB config, not env vars)."""
    from radbot.config.config_loader import config_loader

    with patch.object(
        config_loader,
        "get_agent_config",
        return_value={"main_model": "custom-model"},
    ):
        config = ConfigManager()
        assert config.get_main_model() == "custom-model"


def test_get_main_model_default():
    """Test that main model falls back to hardcoded default."""
    from radbot.config.config_loader import config_loader

    with patch.object(config_loader, "get_agent_config", return_value={}):
        config = ConfigManager()
        assert config.get_main_model() == "gemini-2.5-pro"


def test_get_sub_agent_model():
    """Test retrieving the sub-agent model name (from DB config)."""
    from radbot.config.config_loader import config_loader

    with patch.object(
        config_loader,
        "get_agent_config",
        return_value={"sub_agent_model": "custom-sub"},
    ):
        config = ConfigManager()
        assert config.get_sub_agent_model() == "custom-sub"


def test_is_using_vertex_ai():
    """Test checking if Vertex AI is configured (from DB config)."""
    from radbot.config.config_loader import config_loader

    # Enabled via DB config
    with patch.object(
        config_loader,
        "get_agent_config",
        return_value={"use_vertex_ai": True},
    ):
        config = ConfigManager()
        assert config.is_using_vertex_ai() is True

    # Disabled via DB config
    with patch.object(
        config_loader,
        "get_agent_config",
        return_value={"use_vertex_ai": False},
    ):
        config = ConfigManager()
        assert config.is_using_vertex_ai() is False

    # Default (no DB config)
    with patch.object(config_loader, "get_agent_config", return_value={}):
        config = ConfigManager()
        assert config.is_using_vertex_ai() is False
