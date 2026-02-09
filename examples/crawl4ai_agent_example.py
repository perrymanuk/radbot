#!/usr/bin/env python3
"""
Example script demonstrating the use of Crawl4AI integration with RadBot.

This script creates an agent with Crawl4AI capabilities and demonstrates
ingesting documentation and querying the knowledge base.
"""

import os
import logging
import sys
from dotenv import load_dotenv

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from radbot.agent import create_agent
from radbot.tools.crawl4ai import create_crawl4ai_toolset, test_crawl4ai_connection
from radbot.tools.basic_tools import get_current_time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

def main():
    """Run the example."""
    print("Crawl4AI Agent Example")
    print("=====================\n")
    
    # Check the connection to Crawl4AI
    print("Testing Crawl4AI connection...")
    result = test_crawl4ai_connection()
    
    if not result["success"]:
        print(f"\n❌ Connection failed: {result.get('error', 'Unknown error')}")
        print("Please check your CRAWL4AI_API_URL and CRAWL4AI_API_TOKEN environment variables.")
        return 1
        
    print(f"\n✅ Connection successful! API Version: {result.get('api_version', 'Unknown')}")
    
    # Create an agent with Crawl4AI capabilities
    print("\nCreating agent with Crawl4AI capabilities...")
    tools = [get_current_time]
    crawl4ai_tools = create_crawl4ai_toolset()
    if crawl4ai_tools:
        tools.extend(crawl4ai_tools)
    agent = create_agent(
        tools=tools,
        name="crawl4ai_demo_agent",
        instruction="You are a helpful assistant with web knowledge retrieval capabilities. "
                   "You can ingest web content and answer questions based on the ingested information. "
                   "When asked to look something up, use your crawl4ai tools to ingest and retrieve information."
    )
    
    if not agent:
        print("\n❌ Failed to create agent.")
        return 1
        
    print("\n✅ Agent created successfully!")
    
    # Example conversation loop
    print("\nStarting conversation. Type 'exit' to quit.")
    print('Try asking: "Please ingest https://python.org" and then "What is Python?"')
    print("-" * 50)
    
    user_id = "example_user"
    
    while True:
        user_input = input("\n> ")
        
        if user_input.lower() in ("exit", "quit", "q"):
            break
            
        # Process the message with the agent
        try:
            print("\nProcessing...")
            response = agent.process_message(user_id, user_input)
            print(f"\nAgent: {response}")
        except Exception as e:
            print(f"\n❌ Error: {str(e)}")
    
    print("\nExample completed.")
    return 0

if __name__ == "__main__":
    sys.exit(main())