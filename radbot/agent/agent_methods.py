"""
Methods for RadBotAgent class.

This module provides the implementation of RadBotAgent methods for handling
tool management, message processing, and agent configuration.
"""

import logging
from typing import Any, Dict, List, Optional, Union
from google.genai.types import Content, Part
from google.protobuf.json_format import MessageToDict

# Configure logging
logger = logging.getLogger(__name__)

# Import necessary components
from radbot.agent.agent_base import RadBotAgent

def add_tool(self: RadBotAgent, tool: Any) -> None:
    """
    Add a tool to the agent's capabilities.
    
    Args:
        tool: The tool to add (function, FunctionTool, or MCPToolset)
    """
    # Get current tools and add the new one
    current_tools = list(self.root_agent.tools) if self.root_agent.tools else []
    current_tools.append(tool)
    
    # Update the agent's tools
    self.root_agent.tools = current_tools

def add_tools(self: RadBotAgent, tools: List[Any]) -> None:
    """
    Add multiple tools to the agent's capabilities.
    
    Args:
        tools: List of tools to add
    """
    for tool in tools:
        self.add_tool(tool)

def process_message(self: RadBotAgent, user_id: str, message: str) -> str:
    """
    Process a user message and return the agent's response.
    
    Args:
        user_id: Unique identifier for the user
        message: The user's message
            
    Returns:
        The agent's response as a string
    """
    # Log available tools to help debug
    if self.root_agent and self.root_agent.tools:
        tool_names = []
        for tool in self.root_agent.tools:
            tool_name = getattr(tool, 'name', None) or getattr(tool, '__name__', str(tool))
            tool_names.append(tool_name)
        
        logger.info(f"Processing message with {len(tool_names)} available tools: {', '.join(tool_names[:10])}...")
        
        # Specifically check for Home Assistant tools
        ha_tools = [t for t in tool_names if t.startswith('Hass') or "ha_" in t.lower()]
        if ha_tools:
            logger.info(f"Home Assistant tools available: {', '.join(ha_tools)}")
        else:
            logger.warning("No Home Assistant tools found in the agent!")
    else:
        logger.warning("No tools available to the agent!")
    
    try:
        # Get or create a session with a stable session ID derived from user_id
        session_id = f"session_{user_id[:8]}"
        logger.info(f"Using session ID: {session_id}")
        
        try:
            session = self.session_service.get_session(
                app_name=self.app_name,
                user_id=user_id,
                session_id=session_id
            )
            if not session:
                session = self.session_service.create_session(
                    app_name=self.app_name,
                    user_id=user_id,
                    session_id=session_id
                )
                logger.info(f"Created new session for user {user_id} with ID {session_id}")
            else:
                logger.info(f"Using existing session for user {user_id} with ID {session_id}")
        except Exception as session_error:
            logger.warning(f"Error getting/creating session: {str(session_error)}. Creating new session.")
            session = self.session_service.create_session(
                app_name=self.app_name,
                user_id=user_id,
                session_id=session_id
            )
            logger.info(f"Created new session for user {user_id} with ID {session_id}")
        
        # Create Content object with the user's message
        user_message = Content(
            parts=[Part(text=message)],
            role="user"
        )
        
        # Use the runner to process the message
        logger.info(f"Running agent with message: {message[:50]}{'...' if len(message) > 50 else ''}")
        events = list(self.runner.run(
            user_id=user_id,
            session_id=session.id,  # Include the session ID
            new_message=user_message
        ))
        
        # Extract the agent's text response from the events
        logger.info(f"Received {len(events)} events from runner")
        
        # Find the final response event
        final_response = None
        for event in events:
            # Log the event type for debugging
            logger.debug(f"Event type: {type(event).__name__}")
            
            # Method 1: Check if it's a final response
            if hasattr(event, 'is_final_response') and event.is_final_response():
                logger.debug("Found final response event")
                if hasattr(event, 'content') and event.content:
                    if hasattr(event.content, 'parts') and event.content.parts:
                        for part in event.content.parts:
                            if hasattr(part, 'text') and part.text:
                                final_response = part.text
                                break
                            
            # Method 2: Check for content directly
            if final_response is None and hasattr(event, 'content'):
                logger.debug("Checking event.content for text")
                if hasattr(event.content, 'text') and event.content.text:
                    final_response = event.content.text
                    
            # Method 3: Check for message attribute
            if final_response is None and hasattr(event, 'message'):
                logger.debug("Checking event.message for content")
                if hasattr(event.message, 'content'):
                    final_response = event.message.content
                    
            # Break once we have a final response
            if final_response:
                break
        
        if final_response:
            return final_response
        else:
            logger.warning("No text response found in events")
            return "I apologize, but I couldn't generate a response."
            
    except Exception as e:
        logger.error(f"Error in process_message: {str(e)}", exc_info=True)
        return f"I apologize, but I encountered an error processing your message. Please try again. Error: {str(e)}"

def add_sub_agent(self: RadBotAgent, sub_agent: Any) -> None:
    """
    Add a sub-agent to the main agent.
    
    Args:
        sub_agent: The agent to add as a sub-agent
    """
    # Get current sub-agents
    current_sub_agents = list(self.root_agent.sub_agents) if self.root_agent.sub_agents else []
    current_sub_agents.append(sub_agent)
    
    # Update the agent's sub-agents list
    self.root_agent.sub_agents = current_sub_agents
    
    # Set bidirectional relationships for agent transfers
    if hasattr(sub_agent, 'parent'):
        sub_agent.parent = self.root_agent
    elif hasattr(sub_agent, '_parent'):
        sub_agent._parent = self.root_agent
        
    logger.info(f"Added sub-agent '{sub_agent.name if hasattr(sub_agent, 'name') else 'unnamed'}' to agent '{self.root_agent.name}'")

def get_configuration(self: RadBotAgent) -> Dict[str, Any]:
    """
    Get the current configuration of the agent.
    
    Returns:
        Dictionary containing the agent's configuration
    """
    return {
        "name": self.root_agent.name,
        "model": self.root_agent.model,
        "instruction_name": self.instruction_name,
        "tools_count": len(self.root_agent.tools) if self.root_agent.tools else 0,
        "sub_agents_count": len(self.root_agent.sub_agents) if self.root_agent.sub_agents else 0,
    }

def update_instruction(self: RadBotAgent, new_instruction: str = None, instruction_name: str = None) -> None:
    """
    Update the agent's instruction.
    
    Args:
        new_instruction: The new instruction to set directly
        instruction_name: Name of instruction to load from config
        
    Raises:
        ValueError: If neither new_instruction nor instruction_name is provided
        FileNotFoundError: If instruction_name is provided but not found in config
    """
    if new_instruction:
        self.root_agent.instruction = new_instruction
        self.instruction_name = None
    elif instruction_name:
        try:
            self.root_agent.instruction = self.config.get_instruction(instruction_name)
            self.instruction_name = instruction_name
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Instruction '{instruction_name}' not found in config") from e
    else:
        raise ValueError("Either new_instruction or instruction_name must be provided")

def update_model(self: RadBotAgent, new_model: str) -> None:
    """
    Update the agent's model.
    
    Args:
        new_model: The new model to use (e.g., "gemini-2.5-pro", "gemini-2.0-flash")
    """
    self.root_agent.model = new_model
    self.model = new_model

def reset_session(self: RadBotAgent, user_id: str) -> None:
    """
    Reset a user's session.
    
    Args:
        user_id: The user ID to reset
    """
    # Generate a stable session ID from user_id
    session_id = f"session_{user_id[:8]}"
    
    try:
        # Delete the specific session
        self.session_service.delete_session(
            app_name=self.app_name,
            user_id=user_id,
            session_id=session_id
        )
        logger.info(f"Reset session for user {user_id} with ID {session_id}")
    except Exception as e:
        logger.warning(f"Error resetting session: {str(e)}")

def register_tool_handlers(self: RadBotAgent):
    """Register common tool handlers for the agent."""
    # Only proceed if the agent has register_tool_handler method
    if not hasattr(self.root_agent, 'register_tool_handler'):
        logger.warning("Agent does not support tool handler registration")
        return
        
    try:
        # Import needed components
        from radbot.tools.mcp.mcp_fileserver_client import handle_fileserver_tool_call
        from radbot.tools.memory.memory_tools import search_past_conversations, store_important_information
        
        # Register filesystem tool handlers
        self.root_agent.register_tool_handler(
            "list_files", lambda params: handle_fileserver_tool_call("list_files", params)
        )
        self.root_agent.register_tool_handler(
            "read_file", lambda params: handle_fileserver_tool_call("read_file", params)
        )
        self.root_agent.register_tool_handler(
            "write_file", lambda params: handle_fileserver_tool_call("write_file", params)
        )
        self.root_agent.register_tool_handler(
            "delete_file", lambda params: handle_fileserver_tool_call("delete_file", params)
        )
        self.root_agent.register_tool_handler(
            "get_file_info",
            lambda params: handle_fileserver_tool_call("get_file_info", params),
        )
        self.root_agent.register_tool_handler(
            "search_files", lambda params: handle_fileserver_tool_call("search_files", params)
        )
        self.root_agent.register_tool_handler(
            "create_directory",
            lambda params: handle_fileserver_tool_call("create_directory", params),
        )
        
        # Register memory tools
        self.root_agent.register_tool_handler(
            "search_past_conversations",
            lambda params: MessageToDict(search_past_conversations(params)),
        )
        self.root_agent.register_tool_handler(
            "store_important_information",
            lambda params: MessageToDict(store_important_information(params)),
        )
        
        # In ADK 0.4.0, agent transfers are handled differently
        # No need to explicitly register transfer_to_agent handler
        logger.info("Using ADK 0.4.0 native agent transfer functionality")
        
        logger.info("Registered common tool handlers for agent")
    except Exception as e:
        logger.warning(f"Error registering tool handlers: {str(e)}")

# Attach methods to RadBotAgent class
RadBotAgent.add_tool = add_tool
RadBotAgent.add_tools = add_tools
RadBotAgent.process_message = process_message
RadBotAgent.add_sub_agent = add_sub_agent
RadBotAgent.get_configuration = get_configuration
RadBotAgent.update_instruction = update_instruction
RadBotAgent.update_model = update_model
RadBotAgent.reset_session = reset_session
RadBotAgent.register_tool_handlers = register_tool_handlers