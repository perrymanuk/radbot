"""
Tests for radbotAgent integration with ConfigManager.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

# Import from the current module location
from radbot.agent.agent import (
    FALLBACK_INSTRUCTION,
    AgentFactory,
)
from radbot.agent.agent import (
    RadBotAgent as radbotAgent,  # Use the class name with a lowercase alias for backward compatibility
)
from radbot.agent.agent import (
    create_agent,
    create_runner,
)
from radbot.config.settings import ConfigManager


class TestAgentConfigIntegration:
    """Test cases for agent and config integration."""

    def setup_method(self):
        """Set up test fixtures."""
        # Create a temporary directory for config files
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_dir = Path(self.temp_dir.name)

        # Create instruction directory and files
        instructions_dir = self.config_dir / "instructions"
        instructions_dir.mkdir()

        # Create test instruction file
        test_instruction = (
            "# Test Agent\n\nYou are a test agent with special instructions.\n"
        )
        instruction_path = instructions_dir / "test_instruction.md"
        instruction_path.write_text(test_instruction)

        # Create schemas directory
        schemas_dir = self.config_dir / "schemas"
        schemas_dir.mkdir()

        # Create config manager with test directory
        self.config = ConfigManager(config_dir=self.config_dir)

        # Mock the model config
        self.config.model_config = {
            "main_model": "test-main-model",
            "sub_agent_model": "test-sub-model",
            "use_vertex_ai": False,
        }

    def teardown_method(self):
        """Tear down test fixtures."""
        self.temp_dir.cleanup()

    def test_agent_init_with_config(self):
        """Test agent initialization with config manager."""
        # Create agent with config
        agent = radbotAgent(config=self.config, instruction_name="test_instruction")

        # Verify the agent was configured correctly
        assert agent.model == "test-main-model"
        assert "You are a test agent" in agent.root_agent.instruction
        assert agent.instruction_name == "test_instruction"

    def test_agent_init_fallback(self):
        """Test agent fallback when instruction not found."""
        # Create agent with non-existent instruction name
        agent = radbotAgent(config=self.config, instruction_name="non_existent")

        # Verify fallback instruction was used
        assert agent.model == "test-main-model"
        assert agent.root_agent.instruction == FALLBACK_INSTRUCTION

    def test_agent_factory_root_agent(self):
        """Test AgentFactory.create_root_agent with config."""
        # Create root agent with factory
        root_agent = AgentFactory.create_root_agent(
            instruction_name="test_instruction", config=self.config
        )

        # Verify agent configuration
        assert isinstance(root_agent, Agent)
        assert "You are a test agent" in root_agent.instruction
        assert root_agent.model == "test-main-model"

    def test_agent_factory_sub_agent(self):
        """Test AgentFactory.create_sub_agent with config."""
        # Create sub-agent with factory
        sub_agent = AgentFactory.create_sub_agent(
            name="memory_agent",
            description="Handles memory operations",
            instruction_name="test_instruction",
            config=self.config,
        )

        # Verify agent configuration
        assert isinstance(sub_agent, Agent)
        assert "You are a test agent" in sub_agent.instruction
        assert sub_agent.model == "test-sub-model"
        assert sub_agent.name == "memory_agent"
        assert sub_agent.description == "Handles memory operations"

    def test_factory_sub_agent_fallback(self):
        """Test sub-agent factory fallback instruction."""
        # Create sub-agent with non-existent instruction
        sub_agent = AgentFactory.create_sub_agent(
            name="test_sub",
            description="Test description",
            instruction_name="non_existent",
            config=self.config,
        )

        # Verify minimal instruction was created
        assert "You are a specialized test_sub agent" in sub_agent.instruction
        assert "Test description" in sub_agent.instruction

    def test_create_agent_helper(self):
        """Test create_agent helper function with config."""
        # Create agent with helper
        agent = create_agent(instruction_name="test_instruction", config=self.config)

        # Verify agent configuration
        assert isinstance(agent, radbotAgent)
        assert "You are a test agent" in agent.root_agent.instruction
        assert agent.model == "test-main-model"

    def test_update_instruction_by_name(self):
        """Test updating instruction by name."""
        # Create agent
        agent = radbotAgent(config=self.config)

        # Update instruction by name
        agent.update_instruction(instruction_name="test_instruction")

        # Verify instruction was updated
        assert "You are a test agent" in agent.root_agent.instruction
        assert agent.instruction_name == "test_instruction"

    def test_update_instruction_direct(self):
        """Test updating instruction directly."""
        # Create agent
        agent = radbotAgent(config=self.config)

        # Update instruction directly
        new_instruction = "This is a new direct instruction."
        agent.update_instruction(new_instruction=new_instruction)

        # Verify instruction was updated
        assert agent.root_agent.instruction == new_instruction
        assert agent.instruction_name is None

    def test_update_instruction_error(self):
        """Test error handling when updating instruction."""
        # Create agent
        agent = radbotAgent(config=self.config)

        # Test with missing parameters
        with pytest.raises(ValueError):
            agent.update_instruction()

        # Test with non-existent instruction name
        with pytest.raises(FileNotFoundError):
            agent.update_instruction(instruction_name="non_existent")

    def test_get_configuration(self):
        """Test getting agent configuration."""
        # Create agent
        agent = radbotAgent(config=self.config, instruction_name="test_instruction")

        # Get configuration
        config = agent.get_configuration()

        # Verify configuration
        assert config["name"] == "beto"
        assert config["model"] == "test-main-model"
        assert config["instruction_name"] == "test_instruction"
        assert config["tools_count"] == 0
        assert config["sub_agents_count"] == 0

    def test_agent_with_tools(self):
        """Test agent with tools."""
        # Create mock tools
        mock_tool1 = MagicMock()
        mock_tool2 = MagicMock()

        # Create agent with tools
        agent = radbotAgent(config=self.config, tools=[mock_tool1, mock_tool2])

        # Verify tools were added
        assert len(agent.root_agent.tools) == 2

        # Add another tool
        mock_tool3 = MagicMock()
        agent.add_tool(mock_tool3)

        # Verify tool was added
        assert len(agent.root_agent.tools) == 3

        # Get configuration
        config = agent.get_configuration()
        assert config["tools_count"] == 3

    def test_create_runner(self):
        """Test create_runner with custom session service."""
        # Create mock agent and session service
        mock_agent = MagicMock()
        mock_session_service = MagicMock(spec=InMemorySessionService)

        # Create runner
        runner = create_runner(
            agent=mock_agent, app_name="test-app", session_service=mock_session_service
        )

        # Verify runner configuration
        assert isinstance(runner, Runner)
        assert runner.agent == mock_agent
        assert runner.app_name == "test-app"
        assert runner.session_service == mock_session_service
