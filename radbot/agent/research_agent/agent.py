"""
Research agent implementation.

This module provides the implementation of the research agent, a specialized
agent for technical research and design collaboration.
"""

import logging
import os
from typing import Any, Dict, List, Optional, TypeVar, Union

# Set up logging
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# Import ADK components
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

# Import project components
from radbot.agent.research_agent.instructions import get_full_research_agent_instruction
from radbot.agent.research_agent.sequential_thinking import (
    detect_thinking_trigger,
    process_thinking,
)
from radbot.agent.research_agent.tools import get_research_tools
from radbot.config import config_manager


class ResearchAgent:
    """
    A specialized agent for technical research and design collaboration.

    This agent is designed to:
    1. Perform technical research using web scraping, internal knowledge search, and GitHub
    2. Engage in design discussions as a "rubber duck"
    3. Use sequential thinking to break down complex problems when triggered

    The agent is meant to be used as a sub-agent within a multi-agent system,
    typically receiving tasks from a main coordinator agent.
    """

    def __init__(
        self,
        name: str = "technical_research_agent",
        model: Optional[str] = None,
        instruction: Optional[str] = None,
        description: Optional[str] = None,
        tools: Optional[List[FunctionTool]] = None,
        output_key: Optional[str] = "research_summary",
        enable_sequential_thinking: bool = True,
        enable_google_search: bool = False,
        enable_code_execution: bool = False,
        app_name: str = "beto",
    ):
        """
        Initialize the ResearchAgent.

        Args:
            name: Name of the agent
            model: LLM model to use (defaults to config setting)
            instruction: Agent instruction (defaults to standard research instruction)
            description: Agent description (defaults to standard description)
            tools: List of tools to provide to the agent (defaults to standard research tools)
            output_key: Session state key to store the agent's output (default: "research_summary")
            enable_sequential_thinking: Whether to enable sequential thinking trigger (default: True)
            enable_google_search: Whether to enable Google Search capability (default: False)
            enable_code_execution: Whether to enable Code Execution capability (default: False)
            app_name: Application name for agent transfers, must match parent agent name in ADK 0.4.0+ (default: "beto")
        """
        logger.info(f"Initializing ResearchAgent with name: {name}")

        # Use default model from config if not specified
        if model is None:
            model = config_manager.get_main_model()
            logger.info(f"Using model from config: {model}")

        # Use default instruction if not specified
        if instruction is None:
            instruction = get_full_research_agent_instruction()
            logger.info("Using default research agent instruction")

        # Use default description if not specified
        if description is None:
            description = (
                "A specialized sub-agent for conducting technical research "
                "(web, internal docs, GitHub) and facilitating technical design "
                "discussions (rubber ducking)."
            )
            logger.info("Using default research agent description")

        # Use default research tools if not specified
        if tools is None:
            tools = get_research_tools()
            logger.info(f"Using default research tools: {len(tools)} tools loaded")

        # Create the LlmAgent instance
        self.agent = LlmAgent(
            name=name,  # CRITICAL: Must match exactly what's expected in transfer_to_agent calls
            model=model,
            instruction=instruction,
            description=description,
            tools=tools,
            output_key=output_key,
        )

        # Store app_name for reference (not used by LlmAgent but needed for Runner)
        self.app_name = app_name

        # Save reference to the model name for sequential thinking
        self.model_name = model
        self.enable_sequential_thinking = enable_sequential_thinking

        logger.info(f"ResearchAgent successfully initialized with {len(tools)} tools")
        if self.enable_sequential_thinking:
            logger.info(f"Sequential thinking feature enabled for {name}")

        # Note: enable_google_search and enable_code_execution are accepted
        # for API compatibility but no longer create nested sub-agents.
        # search_agent and code_execution_agent are siblings under beto,
        # and scout can reach them via transfer_to_agent.

    def get_adk_agent(self):
        """
        Get the underlying ADK agent instance.

        Returns:
            LlmAgent: The ADK agent instance
        """
        return self.agent

    def _run_sequential_thinking(self, session: Any, prompt: str) -> Dict[str, Any]:
        """
        Run the sequential thinking process for a given prompt.

        Args:
            session: The ADK session
            prompt: The user's prompt

        Returns:
            Dictionary with thinking process results
        """
        logger.info(
            f"Triggering sequential thinking process for prompt: {prompt[:100]}..."
        )

        # Define a function that uses the same model as the agent for thinking
        def model_fn(thinking_prompt: str) -> str:
            # Use the agent's model directly to get thinking steps
            from google.genai.models import GenerativeModel
            from google.genai.types import GenerationConfig

            try:
                # Initialize the model
                model = GenerativeModel(
                    name=self.model_name,
                    generation_config=GenerationConfig(
                        temperature=0.2,  # Lower temperature for more structured thinking
                        top_p=0.95,
                        top_k=40,
                    ),
                )

                # Get response
                response = model.generate_content(thinking_prompt)
                return response.text
            except Exception as e:
                logger.error(f"Error in model_fn for sequential thinking: {str(e)}")
                # Fallback
                return (
                    f"ERROR: Could not complete sequential thinking process: {str(e)}"
                )

        # Process thinking
        thinking_results = process_thinking(
            prompt=prompt,
            model_fn=model_fn,
            max_steps=6,  # Limited to 6 steps for efficiency
        )

        # Store the thinking process in session state for later reference
        session.state["sequential_thinking"] = thinking_results

        return thinking_results

    def process_prompt(self, session: Any) -> None:
        """
        Pre-process user input to check for sequential thinking triggers.

        This method is called by the LlmAgent before processing the user message,
        allowing us to intercept prompts that should trigger sequential thinking.

        Args:
            session: The ADK session
        """
        # Check if sequential thinking is enabled
        if not self.enable_sequential_thinking:
            return

        # Get the latest user message
        latest_message = session.messages[-1] if session.messages else None
        if not latest_message or latest_message.role != "user":
            return

        prompt = latest_message.content

        # Check if this prompt should trigger sequential thinking
        if detect_thinking_trigger(prompt):
            logger.info("Sequential thinking trigger detected in user prompt")

            # Run sequential thinking process
            thinking_results = self._run_sequential_thinking(session, prompt)

            # Add the thinking process as a structured response from the assistant
            formatted_thinking = thinking_results["thinking_process"]

            # Add thinking results to the response (will be shown in the next message)
            session.response_metadata = {
                "sequential_thinking": True,
                "thinking_process": formatted_thinking,
            }

            # Update the session to include this pre-processed thinking
            session.state["last_thinking_prompt"] = prompt

            logger.info("Sequential thinking process completed and stored in session")
