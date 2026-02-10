"""
Session runner for RadBot web interface.

This module provides the SessionRunner class for managing ADK Runner instances.
"""

import logging
import os
import sys
import json
from typing import Dict, Any, Optional, Union

# Set up logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../../"))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import needed ADK components
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts import InMemoryArtifactService
from google.genai.types import Content, Part

# Import root_agent directly from agent.py
from agent import root_agent

# Import the malformed function handler
from radbot.web.api.malformed_function_handler import extract_text_from_malformed_function

# Import utility functions
from radbot.web.api.session.utils import (
    _extract_response_from_event,
    _process_response_text,
    _get_current_timestamp,
    _get_event_type
)

# Import event processing functions
from radbot.web.api.session.event_processing import (
    _process_tool_call_event,
    _process_agent_transfer_event,
    _process_planner_event,
    _process_model_response_event,
    _process_generic_event,
    _get_plan_step_summary,
    _get_event_details
)

# Import serialization function
from radbot.web.api.session.serialization import _safely_serialize

# Import MCP tools loader
from radbot.web.api.session.mcp_tools import _try_load_mcp_tools

class SessionRunner:
    """Enhanced ADK Runner for web sessions."""
    
    def __init__(self, user_id: str, session_id: str):
        """Initialize a SessionRunner for a specific user.
        
        Args:
            user_id: Unique user identifier
            session_id: Session identifier
        """
        self.user_id = user_id
        self.session_id = session_id
        self.session_service = InMemorySessionService()
        
        # Create artifact service for this session
        self.artifact_service = InMemoryArtifactService()
        logger.info("Created InMemoryArtifactService for the session")
        
        # Try to load MCP tools for this session
        self._try_load_mcp_tools()
        
        # Log agent tree structure
        self._log_agent_tree()
        
        # Create the ADK Runner with app_name matching the agent name
        app_name = root_agent.name if hasattr(root_agent, 'name') else "beto"
        logger.info(f"Using app_name='{app_name}' for session management")
        
        # Get memory service from root_agent if available
        memory_service = None
        if hasattr(root_agent, '_memory_service'):
            memory_service = root_agent._memory_service
            logger.info("Using memory service from root agent")
        elif hasattr(root_agent, 'memory_service'):
            memory_service = root_agent.memory_service
            logger.info("Using memory service from root agent")
        
        # Store memory_service in the global ToolContext class so memory tools can find it
        if memory_service:
            from google.adk.tools.tool_context import ToolContext
            # Set memory_service in the ToolContext class for tools to access
            setattr(ToolContext, "memory_service", memory_service)
            logger.info("Set memory_service in global ToolContext class")
            
        # Create the Runner with artifact service and memory service
        self.runner = Runner(
            agent=root_agent,
            app_name=app_name,
            session_service=self.session_service,
            artifact_service=self.artifact_service,  # Pass artifact service to Runner
            memory_service=memory_service  # Pass memory service to Runner
        )
    
    def _log_agent_tree(self):
        """Log the agent tree structure for debugging."""
        logger.info("===== AGENT TREE STRUCTURE =====")
        
        # Check root agent
        if hasattr(root_agent, 'name'):
            logger.info(f"ROOT AGENT: name='{root_agent.name}'")
        else:
            logger.warning("ROOT AGENT: No name attribute")
        
        # Check sub-agents
        if hasattr(root_agent, 'sub_agents') and root_agent.sub_agents:
            sub_agent_names = [sa.name for sa in root_agent.sub_agents if hasattr(sa, 'name')]
            logger.info(f"SUB-AGENTS: {sub_agent_names}")
            
            # Check each sub-agent
            for i, sa in enumerate(root_agent.sub_agents):
                sa_name = sa.name if hasattr(sa, 'name') else f"unnamed-{i}"
                logger.info(f"SUB-AGENT {i}: name='{sa_name}'")
                
                # Check if sub-agent has its own sub-agents
                if hasattr(sa, 'sub_agents') and sa.sub_agents:
                    sa_sub_names = [ssa.name for ssa in sa.sub_agents if hasattr(ssa, 'name')]
                    logger.info(f"  SUB-AGENTS OF '{sa_name}': {sa_sub_names}")
        else:
            logger.warning("ROOT AGENT: No sub_agents found")
        
        logger.info("===============================")
    
    async def process_message(self, message: str) -> dict:
        """Process a user message and return the agent's response with event data.

        Args:
            message: The user's message text

        Returns:
            Dictionary containing the agent's response text and event data
        """
        try:
            # Create Content object with the user's message
            user_message = Content(
                parts=[Part(text=message)],
                role="user"
            )

            # Get the app_name from the runner
            app_name = self.runner.app_name if hasattr(self.runner, 'app_name') else "beto"

            # Get or create a session with the user_id and session_id
            session = await self.session_service.get_session(
                app_name=app_name,
                user_id=self.user_id,
                session_id=self.session_id
            )

            if not session:
                logger.info(f"Creating new session for user {self.user_id} with app_name='{app_name}'")
                session = await self.session_service.create_session(
                    app_name=app_name,
                    user_id=self.user_id,
                    session_id=self.session_id
                )
                # Load conversation history from DB into the new ADK session
                await self._load_history_into_session(session)
            
            # OPTIMIZATION: Limit event history to reduce context size.
            # Keep a fixed cap so long tool-invocation messages don't carry
            # stale history that confuses the model on the first turn.
            try:
                event_count = len(session.events) if hasattr(session, 'events') else 0
                MAX_EVENTS = 20

                if event_count > MAX_EVENTS:
                    logger.info(f"Truncating event history from {event_count} to {MAX_EVENTS} events")
                    session.events[:] = session.events[-MAX_EVENTS:]
                    logger.info(f"Event history truncated to {len(session.events)} events")
            except Exception as e:
                logger.warning(f"Could not truncate event history: {e}")
            
            # Use the runner to process the message
            logger.info(f"Running agent with message: {message[:50]}{'...' if len(message) > 50 else ''}")
            
            # Log key parameters
            logger.info(f"USER_ID: '{self.user_id}'")
            logger.info(f"SESSION_ID: '{self.session_id}'")
            logger.info(f"APP_NAME: '{app_name}'")
            
            # Set user_id in ToolContext for memory tools
            if hasattr(self.runner, 'memory_service') and self.runner.memory_service:
                from google.adk.tools.tool_context import ToolContext
                setattr(ToolContext, "user_id", self.user_id)
                logger.info(f"Set user_id '{self.user_id}' in global ToolContext")
                
            # Run with consistent parameters (use run_async to avoid blocking the event loop)
            events = []
            async for event in self.runner.run_async(
                user_id=self.user_id,
                session_id=session.id,
                new_message=user_message
            ):
                events.append(event)
            
            # Process events
            logger.info(f"Received {len(events)} events from runner")
            logger.info(f"Event types: {[type(e).__name__ for e in events]}")

            # Log detailed information about each event
            for i, event in enumerate(events):
                # Log is_final_response
                is_final = False
                if hasattr(event, 'is_final_response'):
                    if callable(getattr(event, 'is_final_response')):
                        is_final = event.is_final_response()
                    else:
                        is_final = event.is_final_response
                logger.info(f"Event {i}: is_final={is_final}, content={type(event.content).__name__ if hasattr(event, 'content') else 'N/A'}")

                # Log content parts detail to diagnose text extraction
                if hasattr(event, 'content') and event.content:
                    if hasattr(event.content, 'parts') and event.content.parts:
                        for j, part in enumerate(event.content.parts):
                            part_attrs = []
                            if hasattr(part, 'text') and part.text:
                                part_attrs.append(f"text={part.text[:80]}...")
                            if hasattr(part, 'function_call') and part.function_call:
                                fc = part.function_call
                                name = getattr(fc, 'name', 'unknown')
                                part_attrs.append(f"function_call={name}")
                            if hasattr(part, 'function_response') and part.function_response:
                                fr = part.function_response
                                name = getattr(fr, 'name', 'unknown')
                                part_attrs.append(f"function_response={name}")
                            if not part_attrs:
                                part_attrs.append(f"type={type(part).__name__}, attrs={[a for a in dir(part) if not a.startswith('_')]}")
                            logger.info(f"  Event {i} part {j}: {', '.join(part_attrs)}")
                    else:
                        # Detailed diagnostics for empty content (no parts)
                        role = getattr(event.content, 'role', 'unknown')
                        parts_val = getattr(event.content, 'parts', 'MISSING')
                        is_final = False
                        if hasattr(event, 'is_final_response') and callable(getattr(event, 'is_final_response')):
                            is_final = event.is_final_response()
                        logger.warning(
                            "  Event %d: EMPTY CONTENT — role=%s, parts=%r, is_final=%s, author=%s. "
                            "This may cause session poisoning (subsequent requests can also return empty).",
                            i, role, parts_val, is_final,
                            getattr(event, 'author', 'unknown'),
                        )
                        # Inspect content object for any non-standard attributes
                        content_attrs = {
                            a: repr(getattr(event.content, a, None))[:120]
                            for a in dir(event.content)
                            if not a.startswith('_') and a not in ('parts', 'role')
                            and getattr(event.content, a, None) is not None
                        }
                        if content_attrs:
                            logger.warning("  Event %d: content attrs: %s", i, content_attrs)

                # Log actions (agent transfers) for debugging
                if hasattr(event, 'actions') and event.actions:
                    actions = event.actions
                    if hasattr(actions, 'transfer_to_agent') and actions.transfer_to_agent:
                        logger.info(f"  Event {i}: TRANSFER_TO_AGENT={actions.transfer_to_agent}")
                    if hasattr(actions, 'escalate') and actions.escalate:
                        logger.info(f"  Event {i}: ESCALATE=True")

                # Log author for debugging
                if hasattr(event, 'author'):
                    logger.info(f"  Event {i}: author={event.author}")

            # Initialize variables for collecting event data
            final_response = None
            last_text_response = None  # Track last non-empty text from any model event
            processed_events = []
            raw_response = None

            for event in events:
                # Extract event type and create a base event object
                event_type = _get_event_type(event)
                event_data = {
                    "type": event_type,
                    "timestamp": _get_current_timestamp()
                }

                # Process based on event type
                if event_type == "tool_call":
                    event_data.update(_process_tool_call_event(event))
                elif event_type == "agent_transfer":
                    event_data.update(_process_agent_transfer_event(event))
                elif event_type == "planner":
                    event_data.update(_process_planner_event(event))
                elif event_type == "model_response":
                    event_data.update(_process_model_response_event(event))
                    text = event_data.get("text", "")
                    # Track the last non-empty text from any model response event
                    if text:
                        last_text_response = text
                    # Check if this is the final response - only set if there's actual text
                    if hasattr(event, 'is_final_response') and event.is_final_response():
                        if text:
                            final_response = text
                        # Save raw response for later use if needed
                        if hasattr(event, 'raw_response'):
                            raw_response = event.raw_response
                else:
                    # Generic event processing
                    event_data.update(_process_generic_event(event))

                    # Get raw response if available
                    if hasattr(event, 'raw_response'):
                        raw_response = event.raw_response

                processed_events.append(event_data)

                # Store the event in the events storage
                # Import here to avoid circular imports
                from radbot.web.api.events import add_event
                add_event(self.session_id, event_data)

                # If no final response has been found yet, try to extract it
                if not final_response:
                    extracted = _extract_response_from_event(event)
                    if extracted:
                        final_response = extracted
            
            # If we still don't have a response, check for malformed function calls
            if not final_response and raw_response:
                try:
                    if isinstance(raw_response, str):
                        # Try to parse the raw response as JSON
                        try:
                            raw_response_data = json.loads(raw_response)
                        except json.JSONDecodeError:
                            logger.warning("Could not parse raw response as JSON")
                            raw_response_data = {"raw_text": raw_response}
                    else:
                        raw_response_data = raw_response
                    
                    # Extract text from malformed function call
                    extracted_text = extract_text_from_malformed_function(raw_response_data)
                    if extracted_text:
                        logger.info(f"Recovered text from malformed function call: {extracted_text[:100]}...")
                        final_response = extracted_text
                        
                        # Create a synthetic model response event
                        model_event = {
                            "type": "model_response",
                            "category": "model_response",
                            "timestamp": _get_current_timestamp(),
                            "summary": "Recovered Response from Malformed Function",
                            "text": extracted_text,
                            "is_final": True,
                            "details": {
                                "recovered_from": "malformed_function_call",
                                "session_id": self.session_id
                            }
                        }
                        processed_events.append(model_event)
                        
                        # Add this event to the event storage
                        from radbot.web.api.events import add_event
                        add_event(self.session_id, model_event)
                except Exception as e:
                    logger.error(f"Error processing malformed function call: {str(e)}", exc_info=True)
            
            # Fall back to last non-empty text from any model response event
            if not final_response and last_text_response:
                logger.info("Using last non-empty text from intermediate model response events")
                final_response = last_text_response

            if not final_response:
                # Build a summary of what the model actually returned
                event_summary = []
                for idx, ev in enumerate(events):
                    etype = type(ev).__name__
                    has_content = hasattr(ev, 'content') and ev.content is not None
                    has_parts = has_content and hasattr(ev.content, 'parts') and ev.content.parts
                    parts_count = len(ev.content.parts) if has_parts else 0
                    role = getattr(ev.content, 'role', '?') if has_content else '?'
                    author = getattr(ev, 'author', '?')
                    is_final = False
                    if hasattr(ev, 'is_final_response') and callable(getattr(ev, 'is_final_response')):
                        is_final = ev.is_final_response()
                    event_summary.append(
                        f"  [{idx}] {etype}: author={author}, role={role}, "
                        f"parts={parts_count}, is_final={is_final}"
                    )
                logger.warning(
                    "NO TEXT RESPONSE found in %d events (session=%s). "
                    "This usually means the model returned empty content which will poison "
                    "the session history — all future requests in this session may also fail.\n"
                    "Event breakdown:\n%s",
                    len(events), self.session_id,
                    "\n".join(event_summary) if event_summary else "  (no events)",
                )
                final_response = "I apologize, but I couldn't generate a response."
            
            # Filter events: keep non-model events (tool_call, agent_transfer, etc.)
            # but only include the FINAL model_response to avoid duplicate chat messages
            # and unnecessary API-driven display.
            filtered_events = []
            last_model_event = None
            for ev in processed_events:
                if ev.get("type") == "model_response" or ev.get("category") == "model_response":
                    # Track the latest; prefer one marked as final
                    if ev.get("is_final") or last_model_event is None:
                        last_model_event = ev
                else:
                    filtered_events.append(ev)
            if last_model_event:
                filtered_events.append(last_model_event)

            # Return both the text response and the filtered events
            return {
                "response": final_response,
                "events": filtered_events
            }
        
        except Exception as e:
            logger.error(f"Error in process_message: {str(e)}", exc_info=True)
            error_message = f"I apologize, but I encountered an error processing your message. Please try again. Error: {str(e)}"
            return {
                "response": error_message,
                "events": []
            }
    
    def _extract_response_from_event(self, event):
        """Extract response text from various event types."""
        # Method 1: Check content.parts for text (works for both final and non-final)
        if hasattr(event, 'content') and event.content:
            if hasattr(event.content, 'parts') and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, 'text') and part.text:
                        return self._process_response_text(part.text)

        # Method 2: Check for content.text directly
        if hasattr(event, 'content'):
            if hasattr(event.content, 'text') and event.content.text:
                return self._process_response_text(event.content.text)

        # Method 3: Check for message attribute
        if hasattr(event, 'message'):
            if hasattr(event.message, 'content'):
                return self._process_response_text(event.message.content)

        return None
        
    def _process_response_text(self, text):
        """
        Process response text to handle special content types using web standards approach.
        
        This identifies special content like JSON and wraps it with appropriate 
        data attributes for proper rendering in the frontend.
        
        Args:
            text: The text to process
            
        Returns:
            Processed text with content type annotations
        """
        import re
        import json
        from html import escape
        
        try:
            # First check if this is already HTML content with data attributes
            # If so, return it as is to avoid double-processing
            if '<pre data-content-type=' in text:
                return text
            
            # Check for special JSON responses that need to be preserved as-is
            special_patterns = [
                r'{"call_search_agent_response":', 
                r'{"call_web_search_response":', 
                r'{"function_call_response":'
            ]
            
            # First, check if the entire text is a special JSON response
            is_special_json = False
            for pattern in special_patterns:
                if re.search(pattern, text):
                    is_special_json = True
                    break
                    
            if is_special_json:
                try:
                    # For special JSON that appears to be the full response, wrap the entire thing
                    if text.strip().startswith('{') and text.strip().endswith('}'):
                        # Validate it's actually valid JSON first
                        json.loads(text)
                        
                        # Escape HTML entities
                        safe_json = escape(text)
                        
                        # Wrap in our content-type element
                        return f'<pre data-content-type="json-raw" class="content-json-raw">{safe_json}</pre>'
                    else:
                        # Look for JSON object in the text
                        json_obj_match = re.search(r'({.*})', text, re.DOTALL)
                        if json_obj_match:
                            full_text = text
                            json_str = json_obj_match.group(1)
                            
                            # Validate JSON
                            json.loads(json_str)
                            
                            # Replace the JSON part with wrapped version
                            safe_json = escape(json_str)
                            wrapped_json = f'<pre data-content-type="json-raw" class="content-json-raw">{safe_json}</pre>'
                            
                            # If the JSON is embedded in other text, preserve it
                            result = full_text.replace(json_str, wrapped_json)
                            return result
                except (json.JSONDecodeError, Exception) as e:
                    logger.warning(f"Error processing special JSON: {str(e)}")
                    # If parsing fails, just return the original text
                    return text
            
            # Process regular JSON code blocks in markdown
            code_block_pattern = r'```(?:json)?\s*([\s\S]*?)```'
            modified_text = text
            
            # Find all JSON code blocks
            matches = list(re.finditer(code_block_pattern, text))
            
            # Process in reverse order to avoid index issues when replacing
            for match in reversed(matches):
                block_content = match.group(1)
                # Check if this looks like JSON
                if (block_content.strip().startswith('{') and block_content.strip().endswith('}')) or \
                   (block_content.strip().startswith('[') and block_content.strip().endswith(']')):
                    try:
                        # Try to parse as JSON
                        json_obj = json.loads(block_content)
                        
                        # Check if it's a special JSON content
                        block_text = json.dumps(json_obj)
                        is_special = any(pattern.replace(r'{', '').replace(':', '') in block_text for pattern in special_patterns)
                        
                        if is_special:
                            # For special API responses, preserve exact formatting
                            safe_content = escape(block_content)
                            wrapped_content = f'<pre data-content-type="json-raw" class="content-json-raw">{safe_content}</pre>'
                        else:
                            # For regular JSON, format it nicely
                            formatted = json.dumps(json_obj, indent=2)
                            safe_content = escape(formatted)
                            wrapped_content = f'<pre data-content-type="json-formatted" class="content-json-formatted">{safe_content}</pre>'
                        
                        # Replace the code block with our data-attribute version
                        start, end = match.span()
                        modified_text = modified_text[:start] + wrapped_content + modified_text[end:]
                    except json.JSONDecodeError:
                        # Not valid JSON, leave as is
                        pass
            
            return modified_text
                
        except Exception as e:
            logger.warning(f"Error processing response text: {str(e)}")
            # Return original text if any processing error occurs
            return text
        
    def _get_current_timestamp(self):
        """Get the current timestamp in ISO format."""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    
    def _get_event_type(self, event):
        """Determine the type of event."""
        # For tool events in ADK 0.4.0, check for function_call / tool_calls attribute
        if hasattr(event, 'function_call') or hasattr(event, 'tool_calls'):
            return "tool_call"
            
        # Check for tool result event
        if hasattr(event, 'function_response') or hasattr(event, 'tool_results'):
            return "tool_call"
        
        # Try to get type attribute
        if hasattr(event, 'type'):
            return str(event.type)
        
        # Check for tool call events
        if (hasattr(event, 'tool_name') or 
            (hasattr(event, 'payload') and 
             isinstance(event.payload, dict) and 
             'toolName' in event.payload)):
            return "tool_call"
        
        # Check for agent transfer events
        if (hasattr(event, 'to_agent') or 
            (hasattr(event, 'payload') and 
             isinstance(event.payload, dict) and 
             'toAgent' in event.payload)):
            return "agent_transfer"
        
        # Check for planner events
        if (hasattr(event, 'plan') or 
            (hasattr(event, 'payload') and 
             isinstance(event.payload, dict) and 
             ('plan' in event.payload or 'planStep' in event.payload))):
            return "planner"
        
        # Check for model response events
        if hasattr(event, 'is_final_response'):
            return "model_response"
        
        # Check for content which indicates model response (ADK 0.4.0+)
        if hasattr(event, 'content') or hasattr(event, 'message'):
            return "model_response"
        
        # Default category
        return "other"
    
    def _process_tool_call_event(self, event):
        """Process a tool call event."""
        event_data = {
            "category": "tool_call",
            "summary": "Tool Call"
        }
        
        # Process function call events (ADK 0.4.0+)
        if hasattr(event, 'function_call'):
            function_call = event.function_call
            if hasattr(function_call, 'name'):
                event_data["tool_name"] = function_call.name
                event_data["summary"] = f"Tool Call: {function_call.name}"
            
            if hasattr(function_call, 'args'):
                event_data["input"] = self._safely_serialize(function_call.args)
                
        # Process tool_calls (ADK 0.4.0+)
        elif hasattr(event, 'tool_calls') and event.tool_calls:
            # Use first tool call for display
            tool_call = event.tool_calls[0]
            if hasattr(tool_call, 'name'):
                event_data["tool_name"] = tool_call.name
                event_data["summary"] = f"Tool Call: {tool_call.name}"
            
            if hasattr(tool_call, 'args'):
                event_data["input"] = self._safely_serialize(tool_call.args)
                
        # Process function response / tool results (ADK 0.4.0+)
        elif hasattr(event, 'function_response'):
            if hasattr(event.function_response, 'name'):
                event_data["tool_name"] = event.function_response.name
                event_data["summary"] = f"Tool Response: {event.function_response.name}"
            
            if hasattr(event.function_response, 'response'):
                event_data["output"] = self._safely_serialize(event.function_response.response)
                
        elif hasattr(event, 'tool_results') and event.tool_results:
            # Use first tool result for display
            tool_result = event.tool_results[0]
            if hasattr(tool_result, 'name'):
                event_data["tool_name"] = tool_result.name
                event_data["summary"] = f"Tool Response: {tool_result.name}"
            
            if hasattr(tool_result, 'output'):
                event_data["output"] = self._safely_serialize(tool_result.output)
        
        # Legacy tool call formats
        else:
            # Extract tool name
            if hasattr(event, 'tool_name'):
                event_data["tool_name"] = event.tool_name
                event_data["summary"] = f"Tool Call: {event.tool_name}"
            elif hasattr(event, 'payload') and isinstance(event.payload, dict) and 'toolName' in event.payload:
                event_data["tool_name"] = event.payload['toolName']
                event_data["summary"] = f"Tool Call: {event.payload['toolName']}"
            
            # Extract input
            if hasattr(event, 'input'):
                event_data["input"] = self._safely_serialize(event.input)
            elif hasattr(event, 'payload') and isinstance(event.payload, dict) and 'input' in event.payload:
                event_data["input"] = self._safely_serialize(event.payload['input'])
            
            # Extract output
            if hasattr(event, 'output'):
                event_data["output"] = self._safely_serialize(event.output)
            elif hasattr(event, 'payload') and isinstance(event.payload, dict) and 'output' in event.payload:
                event_data["output"] = self._safely_serialize(event.payload['output'])
        
        # Get the full event for details
        event_data["details"] = self._get_event_details(event)
        
        return event_data
    
    def _process_agent_transfer_event(self, event):
        """Process an agent transfer event."""
        event_data = {
            "category": "agent_transfer",
            "summary": "Agent Transfer"
        }
        
        # Extract to_agent
        to_agent = None
        if hasattr(event, 'to_agent'):
            to_agent = str(event.to_agent)
            event_data["to_agent"] = to_agent
            event_data["summary"] = f"Transfer to: {to_agent}"
        elif hasattr(event, 'payload') and isinstance(event.payload, dict) and 'toAgent' in event.payload:
            to_agent = str(event.payload['toAgent'])
            event_data["to_agent"] = to_agent
            event_data["summary"] = f"Transfer to: {to_agent}"
        
        # Extract from_agent if available
        if hasattr(event, 'from_agent'):
            event_data["from_agent"] = str(event.from_agent)
        elif hasattr(event, 'payload') and isinstance(event.payload, dict) and 'fromAgent' in event.payload:
            event_data["from_agent"] = str(event.payload['fromAgent'])
        
        # Get the basic event details
        event_details = self._get_event_details(event)
        
        # Add model information for the transferred-to agent
        if to_agent:
            # Import here to avoid circular imports
            from radbot.config import config_manager
            
            # Convert agent name to the format expected by config_manager
            agent_config_name = to_agent.lower()
            if agent_config_name == "scout":
                agent_config_name = "scout_agent"
                event_details['model'] = config_manager.get_agent_model(agent_config_name)
            elif agent_config_name in ["code_execution_agent", "search_agent", "todo_agent"]:
                event_details['model'] = config_manager.get_agent_model(agent_config_name)
            elif agent_config_name in ["beto", "radbot"]:
                # Use main model for the root agent
                event_details['model'] = config_manager.get_main_model()
        
        # Add the updated details to the event data
        event_data["details"] = event_details
        
        return event_data
    
    def _process_planner_event(self, event):
        """Process a planner event."""
        event_data = {
            "category": "planner",
            "summary": "Planner Event"
        }
        
        # Extract plan
        if hasattr(event, 'plan'):
            event_data["plan"] = self._safely_serialize(event.plan)
            event_data["summary"] = "Plan Created"
        elif hasattr(event, 'payload') and isinstance(event.payload, dict) and 'plan' in event.payload:
            event_data["plan"] = self._safely_serialize(event.payload['plan'])
            event_data["summary"] = "Plan Created"
        
        # Extract plan step
        if hasattr(event, 'plan_step'):
            event_data["plan_step"] = self._safely_serialize(event.plan_step)
            event_data["summary"] = f"Plan Step: {self._get_plan_step_summary(event.plan_step)}"
        elif hasattr(event, 'payload') and isinstance(event.payload, dict) and 'planStep' in event.payload:
            event_data["plan_step"] = self._safely_serialize(event.payload['planStep'])
            event_data["summary"] = f"Plan Step: {self._get_plan_step_summary(event.payload['planStep'])}"
        
        # Get the full event for details
        event_data["details"] = self._get_event_details(event)
        
        return event_data
    
    def _process_model_response_event(self, event):
        """Process a model response event."""
        event_data = {
            "category": "model_response",
            "summary": "Model Response"
        }
        
        # Extract text from content
        text = ""
        if hasattr(event, 'content') and event.content:
            if hasattr(event.content, 'parts') and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, 'text') and part.text:
                        text += part.text
            elif hasattr(event.content, 'text') and event.content.text:
                text = event.content.text
        
        # Extract text from message
        if not text and hasattr(event, 'message'):
            if hasattr(event.message, 'content'):
                text = event.message.content
        
        event_data["text"] = text
        
        # Check if it's a final response
        if hasattr(event, 'is_final_response') and event.is_final_response():
            event_data["is_final"] = True
            event_data["summary"] = "Final Response"
        else:
            event_data["is_final"] = False
            event_data["summary"] = "Intermediate Response"
            
        # Save raw response if available
        if hasattr(event, 'raw_response'):
            event_data["raw_response"] = event.raw_response
            
        # Try to extract raw response from event internals if not directly available
        if not hasattr(event, 'raw_response'):
            if hasattr(event, '_raw_response'):
                event_data["raw_response"] = event._raw_response
            elif hasattr(event, '_response'):
                event_data["raw_response"] = event._response
            elif hasattr(event, 'response'):
                event_data["raw_response"] = event.response
        
        # Get the basic event details
        event_details = self._get_event_details(event)
        
        # Add model information if not already present
        if 'model' not in event_details:
            # Check if this event is from a specific agent and add its model information
            agent_name = None
            if hasattr(event, 'agent_name'):
                agent_name = event.agent_name
            elif hasattr(event, 'agent'):
                agent_name = event.agent
            
            # Set model information based on agent name
            if agent_name:
                # Import here to avoid circular imports
                from radbot.config import config_manager
                
                # Convert agent name to the format expected by config_manager
                agent_config_name = agent_name.lower()
                if agent_config_name == "scout":
                    agent_config_name = "scout_agent"
                elif agent_config_name in ["beto", "radbot"]:
                    # Use main model for the root agent
                    event_details['model'] = config_manager.get_main_model()
                
                # For specialized agents, get their specific model
                if agent_config_name in ["code_execution_agent", "search_agent", "scout_agent", "todo_agent"]:
                    event_details['model'] = config_manager.get_agent_model(agent_config_name)
        
        # Add the updated details to the event data
        event_data["details"] = event_details
        
        return event_data
    
    def _process_generic_event(self, event):
        """Process a generic event."""
        event_data = {
            "category": "other",
            "summary": "Other Event"
        }
        
        # Try to get a more descriptive summary
        if hasattr(event, '__class__'):
            event_data["summary"] = f"Event: {event.__class__.__name__}"
        
        # Get the full event for details
        event_data["details"] = self._get_event_details(event)
        
        return event_data
    
    def _get_plan_step_summary(self, plan_step):
        """Get a summary string for a plan step."""
        if isinstance(plan_step, dict):
            if 'description' in plan_step:
                return plan_step['description']
            elif 'action' in plan_step:
                return plan_step['action']
        
        # Fallback summary
        return "Plan Step"
    
    def _get_event_details(self, event):
        """Get detailed information about the event."""
        # Try to convert to dict first
        try:
            if hasattr(event, '__dict__'):
                return self._safely_serialize(event.__dict__)
            elif hasattr(event, 'to_dict'):
                return self._safely_serialize(event.to_dict())
            elif hasattr(event, '__str__'):
                return str(event)
        except:
            pass
        
        # Fallback to string representation
        return str(event)
    
    def _try_load_mcp_tools(self):
        """Try to load and add MCP tools to the root agent."""
        try:
            # Import necessary modules
            from radbot.config.config_loader import config_loader
            from radbot.tools.mcp.mcp_client_factory import MCPClientFactory
            from google.adk.tools import FunctionTool
            
            # Get enabled MCP servers
            servers = config_loader.get_enabled_mcp_servers()
            if not servers:
                logger.info("No enabled MCP servers found in configuration")
                return
                
            logger.info(f"Loading tools from {len(servers)} MCP servers")
            
            # Initialize clients and collect tools
            tools_to_add = []
            existing_tool_names = set()
            
            # Get existing tool names
            if hasattr(root_agent, "tools"):
                for tool in root_agent.tools:
                    if hasattr(tool, "name"):
                        existing_tool_names.add(tool.name)
                    elif hasattr(tool, "__name__"):
                        existing_tool_names.add(tool.__name__)
            
            # Go through each server and directly initialize the client
            for server in servers:
                server_id = server.get("id")
                server_name = server.get("name", server_id)
                
                try:
                    # Create a client directly instead of using factory
                    transport = server.get("transport", "sse")
                    url = server.get("url")
                    auth_token = server.get("auth_token")
                    
                    # Handle different transport types
                    if transport == "sse":
                        # Use our custom SSE client implementation
                        from radbot.tools.mcp.client import MCPSSEClient
                        client = MCPSSEClient(url=url, auth_token=auth_token)
                        
                        # Initialize the client (this is synchronous and safe)
                        if client.initialize():
                            # Get tools from the client
                            server_tools = client.tools
                            
                            if server_tools:
                                logger.info(f"Successfully loaded {len(server_tools)} tools from {server_name}")
                                
                                # Add unique tools, filtering out blocklisted ones
                                from radbot.tools.mcp.dynamic_tools_loader import _MCP_TOOL_BLOCKLIST
                                for tool in server_tools:
                                    tool_name = getattr(tool, "name", None) or getattr(tool, "__name__", str(tool))
                                    if tool_name in _MCP_TOOL_BLOCKLIST:
                                        logger.info(f"Skipping blocklisted tool: {tool_name} from {server_name}")
                                    elif tool_name not in existing_tool_names:
                                        tools_to_add.append(tool)
                                        existing_tool_names.add(tool_name)
                                        logger.info(f"Added tool: {tool_name} from {server_name}")
                        else:
                            logger.warning(f"Failed to initialize MCP client for {server_name}")
                            
                    elif transport == "stdio":
                        # For Claude CLI, use the simplified prompt tool implementation
                        try:
                            from radbot.tools.claude_prompt import create_claude_prompt_tool
                            
                            # Get the Claude prompt tool
                            claude_prompt_tool = create_claude_prompt_tool()
                            
                            if claude_prompt_tool:
                                logger.info(f"Successfully loaded Claude prompt tool")
                                
                                # Get the tool name - use multiple approaches to be robust
                                tool_name = None
                                # Try to get name attribute
                                if hasattr(claude_prompt_tool, "name"):
                                    tool_name = claude_prompt_tool.name
                                # Try to get __name__ attribute
                                elif hasattr(claude_prompt_tool, "__name__"):
                                    tool_name = claude_prompt_tool.__name__
                                # Try to get name from _get_declaration().name
                                elif hasattr(claude_prompt_tool, "_get_declaration"):
                                    try:
                                        declaration = claude_prompt_tool._get_declaration()
                                        if hasattr(declaration, "name"):
                                            tool_name = declaration.name
                                    except:
                                        pass
                                # Fallback to string representation
                                if not tool_name:
                                    tool_name = str(claude_prompt_tool)
                                
                                # Add if not already present
                                if tool_name not in existing_tool_names:
                                    tools_to_add.append(claude_prompt_tool)
                                    existing_tool_names.add(tool_name)
                                    logger.info(f"Added tool: {tool_name} from {server_name}")
                                
                                # Successfully loaded prompt tool, no need to try other methods
                                continue
                            else:
                                logger.warning(f"Failed to create Claude prompt tool")
                        except Exception as e:
                            logger.warning(f"Error loading Claude prompt tool: {e}")
                    else:
                        logger.warning(f"Unsupported transport '{transport}' for MCP server {server_name}")
                        
                except Exception as e:
                    logger.warning(f"Error loading tools from MCP server {server_name}: {str(e)}")
            
            # Add all collected tools to the agent
            if tools_to_add and hasattr(root_agent, "tools"):
                root_agent.tools = list(root_agent.tools) + tools_to_add
                logger.info(f"Added {len(tools_to_add)} total MCP tools to agent")
                
        except Exception as e:
            logger.warning(f"Error loading MCP tools: {str(e)}")

    def _safely_serialize(self, obj):
        """Safely serialize objects to JSON-compatible structures."""
        import json
        
        try:
            # Try direct JSON serialization
            json.dumps(obj)
            return obj
        except (TypeError, OverflowError, ValueError):
            # If that fails, try converting to string
            try:
                if hasattr(obj, '__dict__'):
                    return str(obj.__dict__)
                elif hasattr(obj, 'to_dict'):
                    return str(obj.to_dict())
                else:
                    return str(obj)
            except:
                return f"<Unserializable object of type {type(obj).__name__}>"
    
    async def _load_history_into_session(self, session):
        """Load conversation history from the database into an ADK session.

        This seeds the in-memory ADK session with past events so the agent
        retains context across reconnects and page refreshes.

        Args:
            session: The ADK session object to populate.
        """
        try:
            import uuid
            from radbot.web.db import chat_operations
            from google.adk.events import Event

            db_messages = chat_operations.get_messages_by_session_id(
                self.session_id, limit=30
            )
            if not db_messages:
                logger.info(f"No DB history found for session {self.session_id}")
                return

            # Take the last N messages to keep context manageable
            MAX_HISTORY = 15
            recent = db_messages[-MAX_HISTORY:]

            # Get the agent name for model events
            agent_name = root_agent.name if hasattr(root_agent, 'name') else "beto"

            loaded = 0
            # Group user/assistant pairs under the same invocation_id.
            # Each user message starts a new invocation; the following
            # assistant message shares the same id (they're one turn).
            current_invocation_id = str(uuid.uuid4())
            for msg in recent:
                role = msg.get("role", "")
                content_text = msg.get("content", "")
                if not content_text:
                    continue

                if role == "user":
                    # New turn → new invocation id
                    current_invocation_id = str(uuid.uuid4())
                    event = Event(
                        invocation_id=current_invocation_id,
                        author="user",
                        content=Content(parts=[Part(text=content_text)], role="user"),
                    )
                elif role == "assistant":
                    event = Event(
                        invocation_id=current_invocation_id,
                        author=agent_name,
                        content=Content(parts=[Part(text=content_text)], role="model"),
                    )
                else:
                    continue

                await self.session_service.append_event(session, event)
                loaded += 1

            if loaded:
                logger.info(
                    f"Loaded {loaded} events from DB into ADK session {self.session_id}"
                )
        except Exception as e:
            logger.warning(f"Failed to load history from DB into session: {e}", exc_info=True)

    async def reset_session(self):
        """Reset the session conversation history."""
        try:
            # Get the app_name from the runner
            app_name = self.runner.app_name if hasattr(self.runner, 'app_name') else "beto"

            # Delete and recreate the session
            await self.session_service.delete_session(
                app_name=app_name,
                user_id=self.user_id,
                session_id=self.session_id
            )

            # Create a new session
            session = await self.session_service.create_session(
                app_name=app_name,
                user_id=self.user_id,
                session_id=self.session_id
            )

            logger.info(f"Reset session for user {self.user_id}")
            return True
        except Exception as e:
            logger.error(f"Error resetting session: {str(e)}")
            return False
