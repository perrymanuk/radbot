"""
Memory tools for the radbot agent framework.

These tools allow agents to interact with the memory system.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from google.adk.tools.tool_context import ToolContext
from qdrant_client import models

logger = logging.getLogger(__name__)


def _get_memory_service_and_user_id(tool_context):
    """Get memory_service and user_id from the tool context using ADK's invocation context.

    Returns:
        tuple: (memory_service, user_id) - memory_service may be None on failure
    """
    memory_service = None
    user_id = None

    if tool_context:
        # Primary path: access via ADK's invocation context (proper API)
        invocation_ctx = getattr(tool_context, "_invocation_context", None)
        if invocation_ctx:
            memory_service = getattr(invocation_ctx, "memory_service", None)
            user_id = getattr(invocation_ctx, "user_id", None)
            if memory_service:
                logger.info("Found memory_service via invocation context")
            if user_id:
                logger.info(f"Found user_id '{user_id}' via invocation context")

    # Fallback: check global ToolContext class attributes
    if not memory_service:
        logger.warning(
            "Memory service not found in invocation context, checking global ToolContext"
        )
        from google.adk.tools.tool_context import ToolContext as TC

        memory_service = getattr(TC, "memory_service", None)
        if memory_service:
            logger.info("Found memory_service in global ToolContext class")

    # Last resort: create memory service on demand
    if not memory_service:
        try:
            from radbot.memory.qdrant_memory import QdrantMemoryService

            memory_service = QdrantMemoryService()
            logger.info("Created QdrantMemoryService on demand")
        except Exception as e:
            logger.error(f"Failed to create memory service: {str(e)}")

    # Fallback for user_id
    if not user_id:
        from google.adk.tools.tool_context import ToolContext as TC

        user_id = getattr(TC, "user_id", None)
        if user_id:
            logger.info(f"Using user_id '{user_id}' from global ToolContext")
        else:
            logger.warning("No user ID found in any context, using default 'web_user'")
            user_id = "web_user"

    return memory_service, user_id


def search_past_conversations(
    query: str,
    max_results: int = 5,
    time_window_days: Optional[int] = None,
    tool_context: Optional[ToolContext] = None,
    memory_type: Optional[str] = None,
    limit: Optional[int] = None,
    return_stats_only: bool = False,
) -> Dict[str, Any]:
    """
    Search past conversations for relevant information.

    Use this tool when you need to recall previous interactions with the user
    that might be relevant to the current conversation.

    Args:
        query: The search query (what to look for in past conversations)
        max_results: Maximum number of results to return (default: 5)
        time_window_days: Optional time window to restrict search (e.g., 7 for last week)
        tool_context: Tool context for accessing memory service
        memory_type: Type of memory to filter by (e.g., 'conversation_turn', 'user_query')
                     If "all", no filtering by memory type is applied
        limit: Alternative way to specify maximum results (overrides max_results if provided)
        return_stats_only: If True, returns statistics about memory content instead of search results

    Returns:
        dict: A dictionary containing:
              'status' (str): 'success' or 'error'
              'memories' (list, optional): List of relevant past conversations
              'error_message' (str, optional): Description of the error if failed
              'total_memories' (int, optional): If return_stats_only=True, count of all memories
              'memory_types' (list, optional): If return_stats_only=True, list of available memory types
    """
    try:
        memory_service, user_id = _get_memory_service_and_user_id(tool_context)
        if not memory_service:
            return {"status": "error", "error_message": "Memory service not available."}

        # Create filter conditions
        filter_conditions = {}

        # Add time window if specified
        if time_window_days:
            min_timestamp = (
                datetime.now() - timedelta(days=time_window_days)
            ).isoformat()
            filter_conditions["min_timestamp"] = min_timestamp

        # Add memory_type filter if specified and not "all"
        if memory_type and memory_type.lower() != "all":
            filter_conditions["memory_type"] = memory_type

        # Handle return_stats_only to provide memory statistics
        if return_stats_only:
            try:
                # Get collection info to calculate stats
                collection_info = memory_service.client.get_collection(
                    memory_service.collection_name
                )

                # Get a count of all points where user_id matches
                count_filter = models.Filter(
                    must=[
                        models.FieldCondition(
                            key="user_id", match=models.MatchValue(value=user_id)
                        )
                    ]
                )

                count_result = memory_service.client.count(
                    collection_name=memory_service.collection_name,
                    count_filter=count_filter,
                )

                # Get sample of different memory types
                sample_results = memory_service.client.scroll(
                    collection_name=memory_service.collection_name,
                    scroll_filter=count_filter,
                    limit=100,  # Sample size to analyze types
                    with_payload=True,
                )

                # Extract unique memory types
                memory_types = set()
                if sample_results and sample_results[0]:
                    for point in sample_results[0]:
                        if point.payload and "memory_type" in point.payload:
                            memory_types.add(point.payload["memory_type"])

                return {
                    "status": "success",
                    "total_memories": count_result.count,
                    "memory_types": sorted(list(memory_types)),
                    "collection_size": collection_info.points_count,
                }
            except Exception as e:
                logger.error(f"Error getting memory stats: {str(e)}")
                return {
                    "status": "error",
                    "error_message": f"Failed to get memory statistics: {str(e)}",
                }

        # Use limit parameter if provided, otherwise use max_results
        result_limit = limit if limit is not None else max_results

        # Search memories
        # Derive app_name from the invocation context when available
        app_name = "beto"
        if tool_context:
            try:
                app_name = tool_context._invocation_context.app_name or "beto"
            except AttributeError:
                pass

        results = memory_service.search_memory(
            app_name=app_name,
            user_id=user_id,
            query=query,
            limit=result_limit,
            filter_conditions=filter_conditions,
        )

        # Return formatted results
        if results:
            # Format each memory entry for readability
            formatted_results = []
            for entry in results:
                # Basic memory info
                memory_text = entry.get("text", "")
                memory_type = entry.get("memory_type", "unknown")
                relevance = entry.get("relevance_score", 0)

                # Format timestamp if present
                timestamp = entry.get("timestamp", "")
                date_str = ""
                if timestamp:
                    try:
                        # Try to parse the ISO format timestamp
                        dt = datetime.fromisoformat(timestamp)
                        date_str = dt.strftime("%Y-%m-%d %H:%M")
                    except (ValueError, TypeError):
                        date_str = timestamp  # Keep original if parsing fails

                # Add formatted entry
                formatted_entry = {
                    "text": memory_text,
                    "type": memory_type,
                    "relevance_score": relevance,
                    "date": date_str,
                }

                # Add additional fields if present
                if "user_message" in entry:
                    formatted_entry["user_message"] = entry["user_message"]
                if "agent_response" in entry:
                    formatted_entry["agent_response"] = entry["agent_response"]

                formatted_results.append(formatted_entry)

            from radbot.tools.shared.sanitize import sanitize_external_content

            return {
                "status": "success",
                "memories": sanitize_external_content(
                    formatted_results, source="memory"
                ),
            }
        else:
            return {
                "status": "success",
                "memories": [],
                "message": "No relevant memories found.",
            }

    except Exception as e:
        logger.error(f"Error searching past conversations: {str(e)}")
        return {
            "status": "error",
            "error_message": f"Failed to search memory: {str(e)}",
        }


def store_important_information(
    information: str,
    memory_type: str = "important_fact",
    metadata: Optional[Dict[str, Any]] = None,
    tool_context: Optional[ToolContext] = None,
) -> Dict[str, Any]:
    """
    Store important information in memory for future reference.

    Use this tool when the user provides important information that should be
    remembered for future interactions.

    Args:
        information: The text information to store
        memory_type: Type of memory (e.g., 'important_fact', 'user_preference')
        metadata: Additional metadata to store with the information
        tool_context: Tool context for accessing memory service

    Returns:
        dict: A dictionary with status information
    """
    try:
        memory_service, user_id = _get_memory_service_and_user_id(tool_context)
        if not memory_service:
            return {"status": "error", "error_message": "Memory service not available."}

        # Create metadata if not provided
        metadata = metadata or {}
        metadata["memory_type"] = memory_type

        # Create the memory point
        point = memory_service._create_memory_point(
            user_id=user_id, text=information, metadata=metadata
        )

        # Store in Qdrant
        memory_service.client.upsert(
            collection_name=memory_service.collection_name, points=[point], wait=True
        )

        return {
            "status": "success",
            "message": f"Successfully stored information as {memory_type}.",
        }

    except Exception as e:
        logger.error(f"Error storing important information: {str(e)}")
        return {
            "status": "error",
            "error_message": f"Failed to store information: {str(e)}",
        }
