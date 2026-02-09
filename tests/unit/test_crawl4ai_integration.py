"""
Unit tests for the Crawl4AI integration.
"""

import unittest
from unittest.mock import patch, Mock, MagicMock
import os
import json
import asyncio

# Update to use the new import path
from radbot.tools.crawl4ai.mcp_crawl4ai_client import (
    create_crawl4ai_toolset,
    test_crawl4ai_connection,
)


class TestCrawl4AIIntegration(unittest.TestCase):
    """Test cases for Crawl4AI integration."""
    
    def setUp(self):
        """Set up test environment."""
        # Set up mock environment variables
        self.env_patcher = patch.dict(os.environ, {
            "CRAWL4AI_API_URL": "https://crawl4ai.demonsafe.com",
            "CRAWL4AI_API_TOKEN": "test_token"
        })
        self.env_patcher.start()
    
    def tearDown(self):
        """Clean up after tests."""
        # Remove mock environment variables
        self.env_patcher.stop()
    
    @patch('radbot.tools.crawl4ai.mcp_crawl4ai_client.requests.get')
    def test_connection(self, mock_get):
        """Test the connection test function."""
        # Mock the response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "ok",
            "version": "1.0.0"
        }
        mock_get.return_value = mock_response
        
        # Test the function
        result = test_crawl4ai_connection()
        
        # Check the result
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "connected")
        self.assertEqual(result["api_version"], "1.0.0")
        
        # Check that the request was made with the correct parameters
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test_token")
    
    @patch('radbot.tools.crawl4ai.mcp_crawl4ai_client.requests.get')
    def test_connection_error(self, mock_get):
        """Test the connection test function with an error."""
        # Mock a failed response
        mock_get.side_effect = Exception("Connection refused")
        
        # Test the function
        result = test_crawl4ai_connection()
        
        # Check the result
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "connection_error")
        self.assertIn("Connection refused", result["error"])
    
    @patch('radbot.tools.crawl4ai.mcp_crawl4ai_client.create_crawl4ai_toolset_async')
    def test_create_toolset(self, mock_async):
        """Test creating the toolset."""
        # Mock the async function
        mock_async.return_value = (["tool1", "tool2"], MagicMock())
        
        # Test the function
        tools = create_crawl4ai_toolset()
        
        # Check the result
        self.assertEqual(len(tools), 2)
        self.assertEqual(tools[0], "tool1")
        self.assertEqual(tools[1], "tool2")
        
        # Verify the async function was called
        mock_async.assert_called_once()
    
    @patch('radbot.tools.crawl4ai.mcp_crawl4ai_client.asyncio.run')
    def test_ingest_document(self, mock_run):
        """Test the ingest document function."""
        # This requires more complex testing of the async wrapper
        # We'll implement this in the future
        pass

    @patch('radbot.tools.crawl4ai.mcp_crawl4ai_client.asyncio.run')
    def test_query_knowledge(self, mock_run):
        """Test the query knowledge function."""
        # This requires more complex testing of the async wrapper
        # We'll implement this in the future
        pass


if __name__ == "__main__":
    unittest.main()