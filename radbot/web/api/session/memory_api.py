"""
Memory API for RadBot web interface.

This module provides the Memory API for storing and retrieving memories.
"""

import logging
from typing import Dict, Any

from fastapi import Depends, APIRouter, HTTPException, Body
from pydantic import BaseModel

from radbot.web.api.session.session_manager import SessionManager, get_session_manager

# Set up logging
logger = logging.getLogger(__name__)

class MemoryStoreRequest(BaseModel):
    """Request model for storing memories."""
    text: str
    memory_type: str = "important_fact"
    session_id: str

# Create memory API router
memory_router = APIRouter(prefix="/api/memory", tags=["memory"])

@memory_router.post("/store")
async def store_memory(
    request: MemoryStoreRequest,
    session_manager: SessionManager = Depends(get_session_manager)
):
    """Store a memory from the web UI."""
    try:
        logger.info(f"Processing memory store request for session {request.session_id}")
        
        # Get the session runner
        runner = await session_manager.get_runner(request.session_id)
        if not runner:
            logger.warning(f"No session runner found for {request.session_id}")
            raise HTTPException(status_code=404, detail="Session not found")
            
        # Debug runner attributes
        logger.info(f"Runner type: {type(runner).__name__}")
        if hasattr(runner, "runner"):
            logger.info(f"Runner.runner type: {type(runner.runner).__name__}")
            if hasattr(runner.runner, "agent"):
                logger.info(f"Runner.runner.agent type: {type(runner.runner.agent).__name__}")
        
        # Get the memory service - try different locations
        memory_service = None
        
        # First check if the runner has the memory_service directly
        if hasattr(runner, "memory_service") and runner.memory_service:
            memory_service = runner.memory_service
            logger.info("Using memory_service from runner")
        # Next check if the runner.runner has it (from the Runner object)
        elif hasattr(runner, "runner") and hasattr(runner.runner, "memory_service") and runner.runner.memory_service:
            memory_service = runner.runner.memory_service
            logger.info("Using memory_service from runner.runner")
        # Next try to get it from the root_agent
        elif hasattr(runner, "runner") and hasattr(runner.runner, "agent"):
            agent = runner.runner.agent
            if hasattr(agent, "_memory_service") and agent._memory_service:
                memory_service = agent._memory_service
                logger.info("Using _memory_service from agent")
            elif hasattr(agent, "memory_service") and agent.memory_service:
                memory_service = agent.memory_service
                logger.info("Using memory_service from agent")
        
        # Fallback to global ToolContext
        if not memory_service:
            from google.adk.tools.tool_context import ToolContext
            memory_service = getattr(ToolContext, "memory_service", None)
            if memory_service:
                logger.info("Using memory_service from global ToolContext")
        
        # If still not available, try to create a new one
        if not memory_service:
            try:
                # Try to create memory service on demand
                from radbot.memory.qdrant_memory import QdrantMemoryService
                from radbot.config.config_loader import config_loader
                
                # Get Qdrant settings from config_loader
                vector_db_config = config_loader.get_config().get("vector_db", {})
                url = vector_db_config.get("url")
                api_key = vector_db_config.get("api_key")
                host = vector_db_config.get("host", "localhost")
                port = vector_db_config.get("port", 6333)
                collection = vector_db_config.get("collection", "radbot_memories")
                
                # Create and use the memory service
                memory_service = QdrantMemoryService(
                    collection_name=collection,
                    host=host,
                    port=int(port) if isinstance(port, str) else port,
                    url=url,
                    api_key=api_key
                )
                logger.info("Created QdrantMemoryService on demand for memory storage API")
            except Exception as e:
                logger.error(f"Failed to create memory service on demand: {e}")
                
        # If still not available, raise an error
        if not memory_service:
            raise HTTPException(status_code=500, detail="Memory service not available - tried all fallback methods")
        
        user_id = "web_user"
        
        # Instead of creating a ToolContext directly (which changed in ADK versions),
        # use memory_service directly with the store_important_information function
        from google.adk.tools.tool_context import ToolContext
        
        # Set user_id and memory_service in global ToolContext for memory tools to access
        setattr(ToolContext, "user_id", user_id)
        setattr(ToolContext, "memory_service", memory_service)
        
        # Create minimal context dict with required attributes
        tool_context = {
            "user_id": user_id,
            "memory_service": memory_service
        }
        
        # Use the store_important_information function
        from radbot.tools.memory.memory_tools import store_important_information
        
        # Prepare metadata
        metadata = {
            "memory_type": request.memory_type,
            "source": "web_ui_direct",
            "session_id": request.session_id
        }
        
        # Use memory service directly to store the memory
        # This bypasses potential ToolContext compatibility issues
        point = memory_service._create_memory_point(
            user_id=user_id,
            text=request.text,
            metadata=metadata
        )
        
        # Store in Qdrant
        memory_service.client.upsert(
            collection_name=memory_service.collection_name,
            points=[point],
            wait=True
        )
        
        # Return success result
        result = {
            "status": "success",
            "message": f"Successfully stored information as {request.memory_type}."
        }
        
        logger.info(f"Stored memory via web UI: {request.text[:50]}...")
        return result
        
    except Exception as e:
        logger.error(f"Error storing memory: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error storing memory: {str(e)}")