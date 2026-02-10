"""
Custom memory service implementation using Qdrant as the vector database.
"""

import os
import json
import uuid
import logging
from typing import Dict, Any, List, Optional, Union

from dotenv import load_dotenv
import numpy as np
from qdrant_client import QdrantClient, models

# Import ADK components
try:
    from google.adk.sessions import Session
    from google.adk.memory import BaseMemoryService
except ImportError:
    # For testing or standalone use when ADK isn't available
    # Creating stub classes
    class Session:
        """Stub Session class for when ADK isn't available."""
        def __init__(self):
            self.id = ""
            self.user_id = ""
            self.events = []
    
    class BaseMemoryService:
        """Stub BaseMemoryService class for when ADK isn't available."""
        def add_session_to_memory(self, session):
            pass
            
        def search_memory(self, app_name, user_id, query):
            return []

# Import local modules
from radbot.memory.embedding import get_embedding_model, embed_text

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class QdrantMemoryService(BaseMemoryService):
    """
    Memory service implementation using Qdrant as the vector database.
    
    This service implements the ADK BaseMemoryService interface to provide
    persistent memory capabilities for agents.
    """
    
    def __init__(
        self,
        collection_name: str = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        vector_size: Optional[int] = None,  # Will be determined by embedding model
    ):
        """
        Initialize the Qdrant memory service.
        
        Args:
            collection_name: Name of the Qdrant collection to use
            host: Qdrant server host (for local/self-hosted)
            port: Qdrant server port (for local/self-hosted)
            url: Qdrant Cloud URL (for cloud instances)
            api_key: Qdrant Cloud API key (for cloud instances)
            vector_size: Size of embedding vectors (if None, determined from model)
        """
        # Call parent class constructor if BaseMemoryService is real
        if BaseMemoryService.__module__ != '__main__':
            super().__init__()
        
        # Initialize Qdrant client
        try:
            # First priority: Use provided URL and API key
            if url and api_key:
                self.client = QdrantClient(url=url, api_key=api_key, prefer_grpc=False)
                logger.info(f"Connected to Qdrant Cloud at {url} (gRPC disabled)")
            # Second priority: Use provided or environment URL (with or without API key)
            elif url or os.getenv("QDRANT_URL"):
                url = url or os.getenv("QDRANT_URL")
                api_key = api_key or os.getenv("QDRANT_API_KEY")
                # Determine if we should use HTTPS based on URL prefix
                use_https = url.lower().startswith("https://") if url else False
                
                if api_key:
                    self.client = QdrantClient(url=url, api_key=api_key, https=use_https, prefer_grpc=False)
                    logger.info(f"Connected to Qdrant with API key at {url} ({'HTTPS' if use_https else 'HTTP'} mode, gRPC disabled)")
                else:
                    self.client = QdrantClient(url=url, https=use_https, prefer_grpc=False)
                    logger.info(f"Connected to Qdrant at {url} ({'HTTPS' if use_https else 'HTTP'} mode, gRPC disabled)")
            # Last priority: Use host/port (local or self-hosted)
            else:
                host = host or os.getenv("QDRANT_HOST", "localhost")
                port = port or int(os.getenv("QDRANT_PORT", "6333"))
                self.client = QdrantClient(host=host, port=port, prefer_grpc=False)
                logger.info(f"Connected to Qdrant at {host}:{port} (gRPC disabled)")
        except Exception as e:
            logger.error(f"Failed to connect to Qdrant: {str(e)}")
            raise
            
        # Use collection name from environment or default to provided/default value
        self.collection_name = os.getenv("QDRANT_COLLECTION") or collection_name or "radbot_memories"
        logger.info(f"Using collection name: {self.collection_name}")
        
        # Get embedding model info
        self.embedding_model = get_embedding_model()
        self.vector_size = vector_size or self.embedding_model.vector_size
        
        # Initialize collection
        self._initialize_collection()
    
    def _initialize_collection(self):
        """
        Initialize the Qdrant collection if it doesn't exist.
        """
        # Define max retries for operations
        max_retries = 3
        retry_count = 0
        last_error = None
        
        while retry_count < max_retries:
            try:
                # Check if collection exists directly without health check
                # The health check is not consistently available in all versions of the client

                # Check if collection exists
                collections = self.client.get_collections()
                collection_names = [c.name for c in collections.collections]
                
                if self.collection_name in collection_names:
                    # Validate vector dimensions match
                    collection_info = self.client.get_collection(self.collection_name)
                    existing_size = collection_info.config.params.vectors.size
                    if existing_size != self.vector_size:
                        logger.warning(
                            f"Collection '{self.collection_name}' has vector size {existing_size}, "
                            f"expected {self.vector_size}. Recreating collection."
                        )
                        self.client.delete_collection(self.collection_name)
                    else:
                        logger.info(f"Using existing Qdrant collection '{self.collection_name}'")
                        # Ensure source_agent index exists on existing collections
                        try:
                            self.client.create_payload_index(
                                collection_name=self.collection_name,
                                field_name="source_agent",
                                field_schema=models.PayloadSchemaType.KEYWORD
                            )
                            logger.info("Created source_agent index on existing collection")
                        except Exception:
                            pass  # Index already exists
                        return

                # Create the collection
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=self.vector_size,
                        distance=models.Distance.COSINE
                    ),
                    optimizers_config=models.OptimizersConfigDiff(
                        indexing_threshold=10000
                    ),
                    on_disk_payload=True
                )

                # Create payload indexes for common filter fields
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="user_id",
                    field_schema=models.PayloadSchemaType.KEYWORD
                )

                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="timestamp",
                    field_schema=models.PayloadSchemaType.DATETIME
                )

                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="memory_type",
                    field_schema=models.PayloadSchemaType.KEYWORD
                )

                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="source_agent",
                    field_schema=models.PayloadSchemaType.KEYWORD
                )

                logger.info(f"Created Qdrant collection '{self.collection_name}' with vector size {self.vector_size}")
                
                # If we got here, everything succeeded
                return
                
            except Exception as e:
                last_error = e
                retry_count += 1
                logger.warning(f"Qdrant operation attempt {retry_count} failed: {str(e)}")
                
                if retry_count < max_retries:
                    import time
                    # Wait a second before retrying
                    time.sleep(1)
        
        # If we got here, all retries failed
        logger.error(f"Failed to initialize Qdrant collection after {max_retries} attempts: {str(last_error)}")
        raise last_error
    
    def add_session_to_memory(self, session: Session) -> None:
        """
        Process a session and add its contents to the memory store.
        
        This method extracts key information from a session and stores it in Qdrant.
        
        Args:
            session: The session to process and store
        """
        try:
            # Extract user ID from session
            user_id = session.user_id
            
            # Process session events
            points = []
            
            # Only process sessions with events
            if not session.events:
                logger.info(f"No events found in session {session.id}, skipping memory ingestion")
                return
            
            # Extract conversation turns (user message + agent response pairs)
            current_turn = {"user": None, "agent": None}
            
            for event in session.events:
                # Skip non-text events
                if not hasattr(event, 'type') or event.type.name != "TEXT":
                    continue
                    
                role = event.payload.get("author_role")
                text = event.payload.get("text", "")
                
                # Skip empty messages
                if not text.strip():
                    continue
                    
                if role == "user":
                    # If we have a complete previous turn, process it
                    if current_turn["user"] and current_turn["agent"]:
                        turn_point = self._create_memory_point(
                            user_id=user_id,
                            text=f"User: {current_turn['user']}\nAssistant: {current_turn['agent']}",
                            metadata={
                                "memory_type": "conversation_turn",
                                "session_id": session.id,
                                "user_message": current_turn["user"],
                                "agent_response": current_turn["agent"]
                            }
                        )
                        points.append(turn_point)
                        
                    # Start new turn
                    current_turn = {"user": text, "agent": None}
                    
                    # Also store individual user query
                    user_point = self._create_memory_point(
                        user_id=user_id,
                        text=text,
                        metadata={
                            "memory_type": "user_query",
                            "session_id": session.id
                        }
                    )
                    points.append(user_point)
                    
                elif role == "assistant":
                    current_turn["agent"] = text
            
            # Process the final turn if complete
            if current_turn["user"] and current_turn["agent"]:
                turn_point = self._create_memory_point(
                    user_id=user_id,
                    text=f"User: {current_turn['user']}\nAssistant: {current_turn['agent']}",
                    metadata={
                        "memory_type": "conversation_turn",
                        "session_id": session.id,
                        "user_message": current_turn["user"],
                        "agent_response": current_turn["agent"]
                    }
                )
                points.append(turn_point)
            
            # Check if we have points to store
            if not points:
                logger.info(f"No valid text events found in session {session.id}, skipping memory ingestion")
                return
                
            # Store points in Qdrant
            self.client.upsert(
                collection_name=self.collection_name,
                points=points,
                wait=True  # Wait for operation to complete
            )
            
            logger.info(f"Successfully added {len(points)} memory points from session {session.id}")
            
        except Exception as e:
            logger.error(f"Error adding session to memory: {str(e)}")
            # In a production system, consider implementing retry logic or fallback
    
    def _create_memory_point(
        self, 
        user_id: str, 
        text: str, 
        metadata: Optional[Dict[str, Any]] = None
    ) -> models.PointStruct:
        """
        Create a Qdrant point for memory storage.
        
        Args:
            user_id: User identifier
            text: Text content to store
            metadata: Additional metadata for the memory point
            
        Returns:
            A Qdrant PointStruct ready for insertion
        """
        # Create a unique ID for the point
        point_id = str(uuid.uuid4())
        
        # Generate embedding for the text (as a document for agent_memory)
        vector = embed_text(text, self.embedding_model, is_query=False, source="agent_memory")
        
        # Get current timestamp in ISO format
        import datetime
        current_time = datetime.datetime.now().isoformat()
        
        # Create basic payload
        payload = {
            "user_id": user_id,
            "text": text,
            "timestamp": current_time,
            "memory_type": metadata.get("memory_type", "general") if metadata else "general"
        }
        
        # Add additional metadata if provided
        if metadata:
            for key, value in metadata.items():
                if key not in payload:  # Avoid overwriting core fields
                    payload[key] = value
        
        # Create and return the point
        return models.PointStruct(
            id=point_id,
            vector=vector,
            payload=payload
        )
    
    def search_memory(
        self,
        app_name: str,
        user_id: str,
        query: str,
        limit: int = 5,
        filter_conditions: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search the memory store for relevant information.
        
        Args:
            app_name: Name of the application (for multi-app setups)
            user_id: User ID to filter results by
            query: Search query text
            limit: Maximum number of results to return
            filter_conditions: Additional filter conditions for the search
            
        Returns:
            List of relevant memory entries
        """
        try:
            # Generate embedding for the query in the agent_memory context
            query_vector = embed_text(query, self.embedding_model, is_query=True, source="agent_memory")
            
            # Create the filter
            must_conditions = [
                models.FieldCondition(
                    key="user_id",
                    match=models.MatchValue(value=user_id)
                )
            ]
            
            # Add additional filter conditions if provided
            if filter_conditions:
                if "source_agent" in filter_conditions:
                    must_conditions.append(
                        models.FieldCondition(
                            key="source_agent",
                            match=models.MatchValue(value=filter_conditions["source_agent"])
                        )
                    )

                if "memory_type" in filter_conditions:
                    must_conditions.append(
                        models.FieldCondition(
                            key="memory_type",
                            match=models.MatchValue(value=filter_conditions["memory_type"])
                        )
                    )
                
                if "min_timestamp" in filter_conditions:
                    must_conditions.append(
                        models.FieldCondition(
                            key="timestamp",
                            range=models.Range(
                                gte=filter_conditions["min_timestamp"]
                            )
                        )
                    )
                    
                if "max_timestamp" in filter_conditions:
                    must_conditions.append(
                        models.FieldCondition(
                            key="timestamp",
                            range=models.Range(
                                lte=filter_conditions["max_timestamp"]
                            )
                        )
                    )
            
            search_filter = models.Filter(
                must=must_conditions
            )
            
            # Perform the search
            query_response = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                query_filter=search_filter,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )

            # Process the results
            results = []
            for result in query_response.points:
                # Extract the payload
                payload = result.payload
                
                # Create a result entry with the score
                entry = {
                    "text": payload.get("text", ""),
                    "relevance_score": result.score,
                    "memory_type": payload.get("memory_type", "general"),
                    "timestamp": payload.get("timestamp"),
                }
                
                # Add other payload fields
                for key, value in payload.items():
                    if key not in entry and key != "user_id":  # Skip user_id and already added fields
                        entry[key] = value
                
                results.append(entry)
            
            return results
            
        except Exception as e:
            logger.error(f"Error searching memory: {str(e)}")
            return []
    
    def clear_user_memory(self, user_id: str) -> bool:
        """
        Clear all memory entries for a specific user.
        
        Args:
            user_id: The user ID to clear memory for
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Create filter for user_id
            user_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="user_id",
                        match=models.MatchValue(value=user_id)
                    )
                ]
            )
            
            # Delete points matching the filter
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(
                    filter=user_filter
                ),
                wait=True
            )
            
            logger.info(f"Successfully cleared memory for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error clearing user memory: {str(e)}")
            return False