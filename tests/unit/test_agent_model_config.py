"""
Test agent-specific model configuration.
"""

import os
import unittest
from unittest.mock import MagicMock, patch

from radbot.agent.research_agent.factory import create_research_agent
from radbot.config.settings import ConfigManager
from radbot.tools.adk_builtin.code_execution_tool import create_code_execution_agent
from radbot.tools.adk_builtin.search_tool import create_search_agent


class TestAgentModelConfig(unittest.TestCase):
    """Test agent-specific model configuration."""

    def setUp(self):
        """Set up test environment and create a mock config manager."""
        # Create a mock config manager
        self.mock_config = MagicMock(spec=ConfigManager)

        # Set up default model returns
        self.mock_config.get_main_model.return_value = "gemini-2.5-pro"
        self.mock_config.get_sub_agent_model.return_value = "gemini-2.0-flash"
        self.mock_config.is_using_vertex_ai.return_value = True

        # Set up instruction mocks
        self.mock_config.get_instruction.return_value = "Test instruction"

    def test_get_agent_model(self):
        """Test that get_agent_model returns the correct model for each agent type."""
        # Set up the mock config manager to return specific models for each agent
        self.mock_config.get_agent_model.side_effect = lambda agent_name: {
            "code_execution_agent": "gemini-2.5-pro-latest",
            "search_agent": "gemini-2.5-pro",
            "scout_agent": "gemini-2.5-pro-latest",
            "todo_agent": "gemini-2.0-flash",
        }.get(agent_name, self.mock_config.get_sub_agent_model())

        # Verify correct models are returned
        self.assertEqual(
            self.mock_config.get_agent_model("code_execution_agent"),
            "gemini-2.5-pro-latest",
        )
        self.assertEqual(
            self.mock_config.get_agent_model("search_agent"), "gemini-2.5-pro"
        )
        self.assertEqual(
            self.mock_config.get_agent_model("scout_agent"), "gemini-2.5-pro-latest"
        )
        self.assertEqual(
            self.mock_config.get_agent_model("todo_agent"), "gemini-2.0-flash"
        )

        # Verify fallback for unknown agent
        self.mock_config.get_agent_model.side_effect = None
        self.mock_config.get_agent_model.return_value = (
            self.mock_config.get_sub_agent_model()
        )
        self.assertEqual(
            self.mock_config.get_agent_model("unknown_agent"), "gemini-2.0-flash"
        )

    @patch("radbot.tools.adk_builtin.code_execution_tool.config_manager")
    def test_code_execution_agent_model(self, mock_config_manager):
        """Test that the code execution agent uses the correct model."""
        # Configure the mock to return a specific model
        mock_config_manager.get_agent_model.return_value = "gemini-2.5-pro-latest"
        mock_config_manager.get_instruction.return_value = "Test instruction"
        # resolve_model passes Gemini strings through unchanged
        mock_config_manager.resolve_model.side_effect = lambda m: m

        # Create a code execution agent
        agent = create_code_execution_agent()

        # Verify the agent was created with the correct model
        self.assertEqual(agent.model, "gemini-2.5-pro-latest")

        # Verify the get_agent_model was called with the correct agent name
        mock_config_manager.get_agent_model.assert_called_with("code_execution_agent")

    @patch("radbot.tools.adk_builtin.search_tool.config_manager")
    def test_search_agent_model(self, mock_config_manager):
        """Test that the search agent uses the correct model."""
        # Configure the mock to return a specific model
        mock_config_manager.get_agent_model.return_value = "gemini-2.5-pro"
        mock_config_manager.get_instruction.return_value = "Test instruction"
        # resolve_model passes Gemini strings through unchanged
        mock_config_manager.resolve_model.side_effect = lambda m: m

        # Create a search agent
        agent = create_search_agent()

        # Verify the agent was created with the correct model
        self.assertEqual(agent.model, "gemini-2.5-pro")

        # Verify the get_agent_model was called with the correct agent name
        mock_config_manager.get_agent_model.assert_called_with("search_agent")

    @patch("radbot.agent.research_agent.factory.config_manager")
    @patch("radbot.agent.research_agent.factory.ResearchAgent")
    def test_scout_agent_model(self, mock_research_agent, mock_config_manager):
        """Test that the scout agent uses the correct model."""
        # Configure the mock to return a specific model
        mock_config_manager.get_agent_model.return_value = "gemini-2.5-pro-latest"
        mock_config_manager.get_main_model.return_value = "gemini-2.5-pro"
        # resolve_model passes Gemini strings through unchanged
        mock_config_manager.resolve_model.side_effect = lambda m: m

        # Set up the ResearchAgent mock
        mock_instance = MagicMock()
        mock_instance.get_adk_agent.return_value = MagicMock()
        mock_research_agent.return_value = mock_instance

        # Create a research agent
        agent = create_research_agent(as_subagent=True)

        # Verify the get_agent_model was called with the correct agent name
        mock_config_manager.get_agent_model.assert_called_with("scout_agent")

        # Verify ResearchAgent was created with the resolved model
        mock_research_agent.assert_called_with(
            name="scout",
            model="gemini-2.5-pro-latest",
            instruction=None,
            tools=None,
            enable_sequential_thinking=True,
            enable_google_search=False,
            enable_code_execution=False,
            app_name="beto",
        )

    @patch.dict(
        os.environ,
        {
            "RADBOT_CODE_AGENT_MODEL": "env-gemini-2.5-pro-latest",
            "RADBOT_SEARCH_AGENT_MODEL": "env-gemini-2.5-pro",
            "RADBOT_SCOUT_AGENT_MODEL": "env-gemini-2.5-pro-latest",
            "RADBOT_TODO_AGENT_MODEL": "env-gemini-2.0-flash",
        },
    )
    def test_environment_variable_override(self):
        """Test that environment variables override config settings."""
        # Create a real ConfigManager to test env var handling
        config = ConfigManager()

        # Get the agent models from loaded config
        agent_models = config.model_config.get("agent_models", {})

        # Verify environment variables were picked up
        self.assertEqual(
            agent_models.get("code_execution_agent"), "env-gemini-2.5-pro-latest"
        )
        self.assertEqual(agent_models.get("search_agent"), "env-gemini-2.5-pro")
        self.assertEqual(agent_models.get("scout_agent"), "env-gemini-2.5-pro-latest")
        self.assertEqual(agent_models.get("todo_agent"), "env-gemini-2.0-flash")


if __name__ == "__main__":
    unittest.main()
