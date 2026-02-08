"""
Utility functions for RadBot web interface.

This module provides utility functions for the session management.
"""

import logging
import re
import json
from html import escape
from datetime import datetime
from typing import Optional, Any

# Set up logging
logger = logging.getLogger(__name__)

def _extract_response_from_event(event):
    """Extract response text from ADK 0.4.0 event types."""
    # Check if it's a model response event with `message` attribute (ADK 0.4.0)
    if hasattr(event, 'message'):
        if hasattr(event.message, 'content'):
            # Handle string content
            if isinstance(event.message.content, str):
                return _process_response_text(event.message.content)
            # Handle content object with text
            elif hasattr(event.message.content, 'text'):
                return _process_response_text(event.message.content.text)
            # Handle content with parts
            elif hasattr(event.message.content, 'parts') and event.message.content.parts:
                text = ""
                for part in event.message.content.parts:
                    if hasattr(part, 'text') and part.text:
                        text += part.text
                if text:
                    return _process_response_text(text)

    # Check for direct content (ADK 0.4.0)
    if hasattr(event, 'content'):
        # Handle content as string
        if isinstance(event.content, str):
            return _process_response_text(event.content)
        # Handle content object with text
        elif hasattr(event.content, 'text') and event.content.text:
            return _process_response_text(event.content.text)
        # Handle content with parts
        elif hasattr(event.content, 'parts') and event.content.parts:
            text = ""
            for part in event.content.parts:
                if hasattr(part, 'text') and part.text:
                    text += part.text
            if text:
                return _process_response_text(text)

    return None
    
def _process_response_text(text):
    """
    Process response text to handle special content types using web standards approach.
    
    This identifies special content like JSON and wraps it with appropriate 
    data attributes for proper rendering in the frontend.
    
    Args:
        text: The text to process
        
    Returns:
        Processed text with content type annotations
    """
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
    
def _get_current_timestamp():
    """Get the current timestamp in ISO format."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

def _get_event_type(event):
    """Determine the type of event."""
    # Check for actions.transfer_to_agent (ADK 1.x style)
    if hasattr(event, 'actions') and hasattr(event.actions, 'transfer_to_agent') and event.actions.transfer_to_agent:
        return "agent_transfer"

    # ADK 1.x: function calls/responses are in content.parts, not top-level.
    # Use get_function_calls()/get_function_responses() helpers if available.
    if hasattr(event, 'get_function_calls') and event.get_function_calls():
        return "tool_call"
    if hasattr(event, 'get_function_responses') and event.get_function_responses():
        return "tool_call"

    # Fallback: check content.parts directly for function_call/function_response
    if hasattr(event, 'content') and event.content:
        if hasattr(event.content, 'parts') and event.content.parts:
            for part in event.content.parts:
                if hasattr(part, 'function_call') and part.function_call:
                    return "tool_call"
                if hasattr(part, 'function_response') and part.function_response:
                    return "tool_call"

    # Legacy: top-level function_call/function_response (older ADK versions)
    if hasattr(event, 'function_call') or hasattr(event, 'tool_calls'):
        return "tool_call"
    if hasattr(event, 'function_response') or hasattr(event, 'tool_results'):
        return "tool_call"

    # Check for planner events
    if (hasattr(event, 'plan') or
        (hasattr(event, 'payload') and
         isinstance(event.payload, dict) and
         ('plan' in event.payload or 'planStep' in event.payload))):
        return "planner"

    # Check for model response events
    if hasattr(event, 'is_final_response'):
        return "model_response"

    # Check for content which indicates model response
    if hasattr(event, 'content') or hasattr(event, 'message'):
        return "model_response"

    # Default category
    return "other"