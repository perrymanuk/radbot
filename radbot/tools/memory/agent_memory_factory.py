"""
Factory for creating per-agent scoped memory tools.

Each agent gets its own memory namespace via a `source_agent` field in Qdrant metadata.
This allows agents to store and retrieve memories relevant to their domain without
polluting other agents' memory spaces.
"""

import logging
from typing import Dict, Any, Optional, List

from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.tool_context import ToolContext

logger = logging.getLogger(__name__)


def create_agent_memory_tools(agent_name: str) -> List[FunctionTool]:
    """Create memory tools scoped to a specific agent namespace.

    Args:
        agent_name: The agent name used as the source_agent tag in Qdrant.

    Returns:
        List of two FunctionTools: [search_agent_memory, store_agent_memory]
    """

    def _get_memory_service_and_user_id(tool_context):
        """Get memory_service and user_id from the tool context."""
        memory_service = None
        user_id = None

        if tool_context:
            invocation_ctx = getattr(tool_context, '_invocation_context', None)
            if invocation_ctx:
                memory_service = getattr(invocation_ctx, 'memory_service', None)
                user_id = getattr(invocation_ctx, 'user_id', None)

        if not memory_service:
            from google.adk.tools.tool_context import ToolContext as TC
            memory_service = getattr(TC, "memory_service", None)

        if not memory_service:
            try:
                from radbot.memory.qdrant_memory import QdrantMemoryService
                memory_service = QdrantMemoryService()
            except Exception as e:
                logger.error(f"Failed to create memory service: {e}")

        if not user_id:
            from google.adk.tools.tool_context import ToolContext as TC
            user_id = getattr(TC, "user_id", None) or "web_user"

        return memory_service, user_id

    def search_agent_memory(
        query: str,
        max_results: int = 5,
        time_window_days: Optional[int] = None,
        tool_context: Optional[ToolContext] = None,
        memory_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Search memories stored by this agent.

        Use this to recall relevant information from past interactions
        handled by this agent.

        Args:
            query: The search query (what to look for in past memories)
            max_results: Maximum number of results to return (default: 5)
            time_window_days: Optional time window to restrict search (e.g., 7 for last week)
            tool_context: Tool context for accessing memory service
            memory_type: Type of memory to filter by (e.g., 'important_fact', 'user_preference')

        Returns:
            dict with 'status', 'memories', and optionally 'message'
        """
        try:
            memory_service, user_id = _get_memory_service_and_user_id(tool_context)
            if not memory_service:
                return {"status": "error", "error_message": "Memory service not available."}

            filter_conditions = {}

            # Scope to this agent's memories
            filter_conditions["source_agent"] = agent_name

            if time_window_days:
                from datetime import datetime, timedelta
                min_timestamp = (datetime.now() - timedelta(days=time_window_days)).isoformat()
                filter_conditions["min_timestamp"] = min_timestamp

            if memory_type and memory_type.lower() != "all":
                filter_conditions["memory_type"] = memory_type

            results = memory_service.search_memory(
                app_name="beto",
                user_id=user_id,
                query=query,
                limit=max_results,
                filter_conditions=filter_conditions,
            )

            if results:
                from datetime import datetime
                formatted_results = []
                for entry in results:
                    date_str = ""
                    timestamp = entry.get("timestamp", "")
                    if timestamp:
                        try:
                            dt = datetime.fromisoformat(timestamp)
                            date_str = dt.strftime("%Y-%m-%d %H:%M")
                        except (ValueError, TypeError):
                            date_str = timestamp

                    formatted_results.append({
                        "text": entry.get("text", ""),
                        "type": entry.get("memory_type", "unknown"),
                        "relevance_score": entry.get("relevance_score", 0),
                        "date": date_str,
                    })

                from radbot.tools.shared.sanitize import sanitize_external_content
                return {
                    "status": "success",
                    "memories": sanitize_external_content(formatted_results, source="memory"),
                }
            else:
                return {
                    "status": "success",
                    "memories": [],
                    "message": "No relevant memories found.",
                }

        except Exception as e:
            logger.error(f"Error searching agent memory ({agent_name}): {e}")
            return {"status": "error", "error_message": f"Failed to search memory: {e}"}

    def store_agent_memory(
        information: str,
        memory_type: str = "important_fact",
        tool_context: Optional[ToolContext] = None,
    ) -> Dict[str, Any]:
        """
        Store important information in this agent's memory namespace.

        Use this when the user provides important information relevant to
        this agent's domain that should be remembered for future interactions.

        Args:
            information: The text information to store
            memory_type: Type of memory (e.g., 'important_fact', 'user_preference')
            tool_context: Tool context for accessing memory service

        Returns:
            dict with 'status' and 'message'
        """
        try:
            memory_service, user_id = _get_memory_service_and_user_id(tool_context)
            if not memory_service:
                return {"status": "error", "error_message": "Memory service not available."}

            metadata = {
                "memory_type": memory_type,
                "source_agent": agent_name,
            }

            point = memory_service._create_memory_point(
                user_id=user_id,
                text=information,
                metadata=metadata,
            )

            memory_service.client.upsert(
                collection_name=memory_service.collection_name,
                points=[point],
                wait=True,
            )

            return {
                "status": "success",
                "message": f"Successfully stored information as {memory_type}.",
            }

        except Exception as e:
            logger.error(f"Error storing agent memory ({agent_name}): {e}")
            return {"status": "error", "error_message": f"Failed to store information: {e}"}

    return [FunctionTool(search_agent_memory), FunctionTool(store_agent_memory)]
