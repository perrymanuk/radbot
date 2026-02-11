"""
Malformed function call handler for RadBot web API.

This module provides functions to extract text content from malformed function calls,
which can happen when a model tries to execute code directly rather than returning text.
"""

import logging
import re
from typing import Any, Dict, Optional

# Configure logging
logger = logging.getLogger(__name__)


def extract_text_from_malformed_function(
    response_data: Dict[str, Any],
) -> Optional[str]:
    """
    Extracts meaningful text from a malformed function call in the model response.

    Args:
        response_data: The raw response data from the model

    Returns:
        Extracted text if a malformed function call was found, otherwise None
    """
    # Check if there's a malformed function call in the response
    if not isinstance(response_data, dict):
        return None

    # Look for candidates
    candidates = response_data.get("candidates", [])
    if not candidates or not isinstance(candidates, list):
        return None

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue

        # Check if this is a malformed function call response
        finish_reason = candidate.get("finish_reason")
        if finish_reason != "MALFORMED_FUNCTION_CALL":
            continue

        # Get the malformed function content
        malformed_content = candidate.get("finish_message")
        if not malformed_content:
            continue

        logger.info(f"Found malformed function call: {malformed_content[:100]}...")

        # Extract text content from malformed function call (usually print statements)
        text = extract_text_from_print_statements(malformed_content)

        if text:
            logger.info(f"Successfully extracted text from malformed function call")
            return text

    return None


def extract_text_from_print_statements(content: str) -> Optional[str]:
    """
    Extracts text from print() statements in malformed function calls.

    Args:
        content: The malformed function call content

    Returns:
        Extracted text from print statements or the original content
    """
    if not content:
        return None

    # Check if content contains print statements
    if "print(" not in content:
        return content

    # Extract content from print statements
    result = []
    lines = content.strip().split("\n")

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Try to extract content from print("text") statements
        match = re.search(r'print\s*\(\s*[\'"](.+?)[\'"]\s*\)', line)
        if match:
            result.append(match.group(1))
            continue

        # For more complex print statements, try a simpler approach
        if line.startswith("print(") and line.endswith(")"):
            # Remove print( and )
            inner_content = line[6:-1].strip()

            # Handle quoted strings (simple case)
            if (inner_content.startswith('"') and inner_content.endswith('"')) or (
                inner_content.startswith("'") and inner_content.endswith("'")
            ):
                result.append(inner_content[1:-1])
                continue

        # Fall back to keeping the line as is for complex cases
        if line.startswith("print("):
            # Just add some basic cleanup
            line = line.replace("print(", "").rstrip(")").strip()
            if line.startswith('"') and line.endswith('"'):
                line = line[1:-1]
            elif line.startswith("'") and line.endswith("'"):
                line = line[1:-1]
            result.append(line)

    if result:
        return "\n".join(result)

    # If we couldn't extract anything useful, return the original content
    return content
