#!/usr/bin/env python3
"""
Crawl4AI Vector Store module for radbot.

This module provides integration between Crawl4AI and Qdrant for vector search
capabilities, allowing semantic search of crawled web content.
"""

import os
import re
import logging
import uuid
from typing import Dict, Any, List, Optional, Tuple

from dotenv import load_dotenv
from qdrant_client import QdrantClient, models

# Import local modules
from radbot.memory.embedding import get_embedding_model, embed_text, EmbeddingModel

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class Crawl4AIVectorStore:
    """
    Vector database storage for Crawl4AI content using Qdrant.
    
    This class provides methods for storing crawled content from Crawl4AI
    in a vector database (Qdrant) to enable semantic search capabilities.
    """
    
    def __init__(
        self,
        collection_name: str = "crawl4ai_docs",
        host: Optional[str] = None,
        port: Optional[int] = None,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        """
        Initialize the Crawl4AI vector store.
        
        Args:
            collection_name: Name of the Qdrant collection to use
            host: Qdrant server host (default: from env or localhost)
            port: Qdrant server port (default: from env or 6333)
            url: Qdrant Cloud URL (default: from env)
            api_key: Qdrant Cloud API key (default: from env)
        """
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
            
        # Use collection name from environment or default to provided value
        self.collection_name = os.getenv("CRAWL4AI_COLLECTION") or collection_name
        logger.info(f"Using collection name: {self.collection_name}")
        
        # Get embedding model
        self.embedding_model = get_embedding_model()
        
        # Initialize collection
        self._initialize_collection()
    
    def _initialize_collection(self) -> None:
        """Initialize the Qdrant collection if it doesn't exist."""
        try:
            # Check if collection exists
            collections = self.client.get_collections()
            collection_names = [c.name for c in collections.collections]
            
            if self.collection_name not in collection_names:
                # Create the collection
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=self.embedding_model.vector_size,
                        distance=models.Distance.COSINE
                    ),
                    # Configure optimizers for better performance
                    optimizers_config=models.OptimizersConfigDiff(
                        indexing_threshold=10000  # Good balance for medium collections
                    ),
                    on_disk_payload=True  # Store payloads on disk to save RAM
                )
                
                # Create payload indexes for common filter fields
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="url",
                    field_schema=models.PayloadSchemaType.KEYWORD
                )
                
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="timestamp",
                    field_schema=models.PayloadSchemaType.DATETIME
                )
                
                logger.info(f"Created Qdrant collection '{self.collection_name}'")
            else:
                logger.info(f"Using existing Qdrant collection '{self.collection_name}'")
                
        except Exception as e:
            logger.error(f"Failed to initialize Qdrant collection: {str(e)}")
            raise
    
    def split_into_chunks(self, markdown_text: str, max_chunk_size: int = 800) -> List[str]:
        """
        Split markdown text into chunks based on headings.
        
        Args:
            markdown_text: Markdown text to split
            max_chunk_size: Maximum size of each chunk in characters
            
        Returns:
            List of text chunks
        """
        # Split by headings
        chunks = re.split(r'(#{1,6}\s+.*)', markdown_text)
        
        # Combine heading with its content
        processed_chunks = []
        current_chunk = ""
        
        for chunk in chunks:
            # If this is a heading
            if re.match(r'#{1,6}\s+.*', chunk):
                if current_chunk:
                    processed_chunks.append(current_chunk)
                current_chunk = chunk
            else:
                # If adding this chunk would make the current chunk too large
                if len(current_chunk) + len(chunk) > max_chunk_size:
                    # If current chunk is not empty, add it to processed_chunks
                    if current_chunk:
                        processed_chunks.append(current_chunk)
                    
                    # If the new chunk is too large on its own, split it by paragraphs
                    if len(chunk) > max_chunk_size:
                        paragraphs = chunk.split('\n\n')
                        temp_chunk = ""
                        
                        for paragraph in paragraphs:
                            if len(temp_chunk) + len(paragraph) + 2 <= max_chunk_size:  # +2 for '\n\n'
                                temp_chunk += paragraph + ("\n\n" if temp_chunk else "")
                            else:
                                if temp_chunk:
                                    processed_chunks.append(temp_chunk)
                                
                                # If a single paragraph is too large, split by sentences
                                if len(paragraph) > max_chunk_size:
                                    sentences = re.split(r'(?<=[.!?])\s+', paragraph)
                                    temp_chunk = ""
                                    
                                    for sentence in sentences:
                                        if len(temp_chunk) + len(sentence) + 1 <= max_chunk_size:  # +1 for space
                                            temp_chunk += sentence + (" " if temp_chunk else "")
                                        else:
                                            if temp_chunk:
                                                processed_chunks.append(temp_chunk)
                                            
                                            # If a single sentence is still too large, just truncate it
                                            if len(sentence) > max_chunk_size:
                                                # Split into chunks of max_chunk_size
                                                for i in range(0, len(sentence), max_chunk_size):
                                                    processed_chunks.append(sentence[i:i+max_chunk_size])
                                            else:
                                                temp_chunk = sentence
                                    
                                    if temp_chunk:
                                        processed_chunks.append(temp_chunk)
                                else:
                                    temp_chunk = paragraph
                        
                        if temp_chunk:
                            processed_chunks.append(temp_chunk)
                        
                        current_chunk = ""
                    else:
                        current_chunk = chunk
                else:
                    current_chunk += chunk
        
        # Add the last chunk if it exists
        if current_chunk:
            processed_chunks.append(current_chunk)
        
        # Final validation to ensure no chunk exceeds max_chunk_size
        final_chunks = []
        for chunk in processed_chunks:
            if len(chunk) > max_chunk_size:
                # Split by paragraphs as a last resort
                for i in range(0, len(chunk), max_chunk_size):
                    final_chunks.append(chunk[i:i+max_chunk_size])
            else:
                final_chunks.append(chunk)
        
        return final_chunks

    def add_document(
        self, 
        url: str, 
        title: str, 
        content: str, 
        chunk_size: int = 800
    ) -> Dict[str, Any]:
        """
        Add a document to the vector store.
        
        Args:
            url: URL of the document
            title: Title of the document
            content: Markdown content of the document
            chunk_size: Maximum size of each chunk in characters
            
        Returns:
            Dictionary with results of the operation
        """
        try:
            # First check if document already exists by URL
            self.delete_document(url)
            
            # Split content into chunks
            logger.info(f"Splitting content from {url} into chunks")
            chunks = self.split_into_chunks(content, max_chunk_size=chunk_size)
            
            if not chunks:
                return {
                    "success": False, 
                    "message": "No valid content chunks to index",
                    "chunks_count": 0
                }
            
            # Create points for each chunk
            points = []
            
            # Get current timestamp
            import datetime
            current_time = datetime.datetime.now().isoformat()
            
            for i, chunk in enumerate(chunks):
                # Skip chunks that are too small
                if len(chunk.strip()) < 50:
                    continue
                
                # Generate a unique ID for the chunk
                chunk_id = str(uuid.uuid4())
                
                # Generate embedding for the chunk (as a document for crawl4ai)
                vector = embed_text(chunk, self.embedding_model, is_query=False, source="crawl4ai")
                
                # Create point
                point = models.PointStruct(
                    id=chunk_id,
                    vector=vector,
                    payload={
                        "url": url,
                        "title": title,
                        "content": chunk,
                        "timestamp": current_time,
                        "chunk_index": i
                    }
                )
                
                points.append(point)
            
            if not points:
                return {
                    "success": False, 
                    "message": "No substantial content chunks to index",
                    "chunks_count": 0
                }
            
            # Insert data into Qdrant
            logger.info(f"Inserting {len(points)} points into Qdrant collection '{self.collection_name}'")
            self.client.upsert(
                collection_name=self.collection_name,
                points=points,
                wait=True  # Wait for operation to complete
            )
            
            return {
                "success": True,
                "message": f"Successfully indexed {len(points)} chunks from {url}",
                "chunks_count": len(points)
            }
            
        except Exception as e:
            logger.error(f"Error adding document to vector store: {str(e)}")
            return {
                "success": False,
                "message": f"Error adding document: {str(e)}",
                "chunks_count": 0
            }
    
    def search(
        self, 
        query: str, 
        limit: int = 5
    ) -> Dict[str, Any]:
        """
        Search for documents by semantic similarity.
        
        Args:
            query: Search query text
            limit: Maximum number of results to return
            
        Returns:
            Dictionary with search results
        """
        try:
            logger.info(f"Searching for: {query}")
            
            # Check count of documents before search
            doc_count = self.count_documents()
            logger.info(f"Current document count in vector store: {doc_count}")
            
            if doc_count == 0:
                logger.warning("Vector store is empty! No documents to search.")
                return {
                    "success": False,
                    "message": "Cannot search - no documents have been stored in the knowledge base. Please ingest content first using crawl4ai_ingest_url.",
                    "results": [],
                    "count": 0
                }
                
            # Generate embedding for the query in crawl4ai context
            query_vector = embed_text(query, self.embedding_model, is_query=True, source="crawl4ai")
            
            # Perform the search
            logger.info(f"Performing vector search in collection '{self.collection_name}'")
            query_response = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )

            # Log search stats
            logger.info(f"Search returned {len(query_response.points)} results")

            # Process the results
            results = []
            for result in query_response.points:
                # Extract the payload
                payload = result.payload
                
                # Create a result entry with the score
                entry = {
                    "url": payload.get("url", ""),
                    "title": payload.get("title", ""),
                    "content": payload.get("content", ""),
                    "similarity": result.score,
                    "timestamp": payload.get("timestamp"),
                }
                
                results.append(entry)
            
            return {
                "success": True,
                "results": results,
                "count": len(results)
            }
            
        except Exception as e:
            logger.error(f"Error searching vector store: {str(e)}")
            return {
                "success": False,
                "message": f"Error searching: {str(e)}",
                "results": []
            }
    
    def delete_document(self, url: str) -> Dict[str, Any]:
        """
        Delete a document from the vector store by URL.
        
        Args:
            url: URL of the document to delete
            
        Returns:
            Dictionary with results of the operation
        """
        try:
            # Create filter for URL
            url_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="url",
                        match=models.MatchValue(value=url)
                    )
                ]
            )
            
            # Delete points matching the filter
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(
                    filter=url_filter
                ),
                wait=True
            )
            
            logger.info(f"Deleted document with URL {url}")
            return {
                "success": True,
                "message": f"Deleted document with URL {url}"
            }
            
        except Exception as e:
            logger.error(f"Error deleting document: {str(e)}")
            return {
                "success": False,
                "message": f"Error deleting document: {str(e)}"
            }
    
    def count_documents(self) -> int:
        """Return the number of documents in the collection."""
        try:
            # Check if collection exists by getting all collections
            collections = self.client.get_collections()
            collection_names = [c.name for c in collections.collections]
            
            if self.collection_name not in collection_names:
                logger.warning(f"Collection '{self.collection_name}' doesn't exist yet")
                return 0
                
            # Collection exists, count the documents
            count_response = self.client.count(self.collection_name)
            count = count_response.count if hasattr(count_response, 'count') else 0
            
            if count == 0:
                logger.warning(f"Collection '{self.collection_name}' exists but is empty")
            else:
                logger.info(f"Collection '{self.collection_name}' has {count} documents")
            return count
        except Exception as e:
            logger.error(f"Error counting documents: {str(e)}")
            return 0

def get_crawl4ai_vector_store() -> Crawl4AIVectorStore:
    """
    Get a Crawl4AI vector store instance.
    
    Returns:
        Crawl4AIVectorStore instance
    """
    # Get collection name from environment or use default
    collection_name = os.getenv("CRAWL4AI_COLLECTION", "crawl4ai_docs")
    
    return Crawl4AIVectorStore(collection_name=collection_name)


def test_vector_store() -> None:
    """Test vector store functionality with a sample document."""
    print("Testing Crawl4AI Vector Store...")
    
    try:
        # Initialize vector store
        vector_store = get_crawl4ai_vector_store()
        
        # Add test document
        test_url = "https://example.com/test"
        test_title = "Test Document"
        test_content = """
        # Test Document
        
        This is a test document for the Crawl4AI vector store.
        
        ## Section 1
        
        This is section 1 content about semantic search in Qdrant.
        
        ## Section 2
        
        This is section 2 content about vector databases and embeddings.
        """
        
        result = vector_store.add_document(
            url=test_url, 
            title=test_title,
            content=test_content
        )
        print(f"Add document result: {result}")
        
        # Search for documents
        search_result = vector_store.search("semantic search")
        print(f"Search results: {search_result}")
        
        # Count documents
        count = vector_store.count_documents()
        print(f"Document count: {count}")
        
        # Delete test document
        delete_result = vector_store.delete_document(test_url)
        print(f"Delete result: {delete_result}")
        
        print("Crawl4AI vector store test completed successfully")
        
    except Exception as e:
        print(f"Error testing vector store: {str(e)}")


if __name__ == "__main__":
    test_vector_store()