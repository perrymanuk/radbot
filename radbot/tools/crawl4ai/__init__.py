"""
Crawl4AI Integration for Radbot

This package provides integration with Crawl4AI service through the Model Context Protocol (MCP).
It enables web content ingestion, storage, and semantic search capabilities.
"""

from .mcp_crawl4ai_client import (
    create_crawl4ai_toolset,
    test_crawl4ai_connection,
    get_crawl4ai_config,
)

from .crawl4ai_two_step_crawl import crawl4ai_two_step
from .crawl4ai_vector_store import get_crawl4ai_vector_store, Crawl4AIVectorStore

__all__ = [
    'create_crawl4ai_toolset',
    'test_crawl4ai_connection',
    'get_crawl4ai_config',
    'crawl4ai_two_step',
    'get_crawl4ai_vector_store',
    'Crawl4AIVectorStore',
]
