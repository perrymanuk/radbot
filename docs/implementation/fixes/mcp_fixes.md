# MCP Integration Fixes

<!-- Version: 0.4.0 | Last Updated: 2025-05-07 -->


This document consolidates the various fixes implemented for Model Context Protocol (MCP) integration in the RadBot framework.

## Overview

The RadBot framework uses the Model Context Protocol (MCP) to integrate with various external services, including:

1. **MCP Fileserver** - For filesystem operations
2. **Home Assistant** - For smart home control

Several issues were encountered and fixed during the implementation and evolution of these integrations, particularly related to:

- ADK version compatibility (0.3.0 to 0.4.0)
- Asynchronous execution in different contexts
- Import paths after code restructuring
- API changes in MCP libraries
- Agent transfer functionality

## ADK 0.3.0/0.4.0 Compatibility

### Issues

1. **QueryResponse Class Migration**: The ADK moved response-related classes from `agents` module to `events` module
2. **Function Response Structure**: Changed from `function_response` to `function_call_event` parameter
3. **MCP Client API Changes**: The MCP Python SDK API evolved with changes to the client interface

### Fixes

1. **Updated Import Statements**:
   ```python
   # Before
   from google.adk.agents import QueryResponse
   
   # After
   from google.adk.events import Event
   ```

2. **Updated Function Return Types**:
   ```python
   # Before
   def handle_fileserver_tool_call(...) -> QueryResponse:
   
   # After
   def handle_fileserver_tool_call(...) -> Event:
   ```

3. **Updated Response Object Creation**:
   ```python
   # Before
   return QueryResponse(function_response={...})
   
   # After
   return Event(function_call_event={...})
   ```

4. **Updated MCP Client Initialization**:
   ```python
   # Before
   from mcp.client import Client
   client = Client()
   
   # After
   from mcp.client.session import ClientSession
   from mcp.client.transports.stdio import stdio_client
   transport = await stdio_client(...)
   client = ClientSession(transport)
   await client.initialize()
   ```

5. **Updated Tool Import Path**:
   ```python
   # Before
   from mcp.server.lowlevel.tool import Tool
   
   # After
   from mcp.types import Tool
   ```

## MCP Fileserver Async Fix

### Issues

1. **Positional Arguments Mismatch**:
   ```
   Error creating MCP fileserver toolset: start_server_async() takes from 1 to 3 positional arguments but 4 were given
   ```

2. **Backend Hanging**:
   The backend would hang when creating the MCP fileserver toolset inside an existing event loop, particularly when called from the web application.

### Root Causes

1. **Function Signature Mismatch**: Different parameter requirements between the client and server functions
2. **Event Loop Conflicts**: Trying to start a new event loop inside an existing one
3. **Python Subprocess Issues**: Using a Python subprocess in an already running Python environment

### Solutions

1. **Updated Server Function Signature**:
   ```python
   # Before
   async def start_server_async(root_dir, allow_write, allow_delete):
   
   # After
   async def start_server_async(exit_stack, root_dir, allow_write, allow_delete):
   ```

2. **Improved Async Thread Management**:
   ```python
   def run_async_in_thread(coro):
       """Run an asynchronous coroutine in a separate thread."""
       # Create a new event loop for the executor to prevent conflicts
       def run_with_new_loop(coro):
           new_loop = asyncio.new_event_loop()
           asyncio.set_event_loop(new_loop)
           try:
               return new_loop.run_until_complete(coro)
           finally:
               new_loop.close()
               
       with ThreadPoolExecutor(max_workers=1) as executor:
           future = executor.submit(run_with_new_loop, coro)
           return future.result()
   ```

3. **Simplified Transport for Development**:
   ```python
   client_transport = await exit_stack.enter_async_context(
       stdio_client(StdioServerParameters(
           command='/bin/cat',  # Simple command that will be replaced by the server's stdio
           args=[],
           env={}
       ))
   )
   ```

4. **Alternative Approach for Async Contexts**:
   For web server contexts, we created tool stubs instead of attempting to start a real MCP server:
   ```python
   # Instead of using the complex async method in a thread, which can hang,
   # create simplified tool stubs with proper descriptions
   tools = [
       FunctionTool(
           name="list_files",
           description="List files and directories in a path",
           parameters={...}
       ),
       # ...additional tools...
   ]
   ```

## MCP Tools Import Fixes

### Issues

1. **Class Name Mismatch**:
   ```
   cannot import name 'MCPFileServer' from 'radbot.tools.mcp.mcp_fileserver_server'
   ```

2. **Missing Functions**:
   ```
   cannot import name 'get_available_mcp_tools' from 'radbot.tools.mcp.mcp_tools'
   ```

### Root Causes

1. **Class Name Inconsistency**: The `__init__.py` file was trying to import a class called `MCPFileServer`, but the actual class was named `FileServerMCP`.
2. **Missing Functions**: Required functions were missing after restructuring:
   - `get_available_mcp_tools` from `mcp_tools.py`
   - `convert_to_adk_tool` from `mcp_utils.py`

### Solutions

1. **Updated Import Statements**:
   ```python
   # Before
   from radbot.tools.mcp.mcp_fileserver_server import MCPFileServer
   
   # After
   from radbot.tools.mcp.mcp_fileserver_server import FileServerMCP
   ```

2. **Added Missing Functions**:
   ```python
   def get_available_mcp_tools() -> List[Any]:
       """Get a list of all available MCP tools."""
       tools = []
       
       # Try to get Home Assistant tools
       # Try to get FileServer tools
       
       return tools
   
   def convert_to_adk_tool(function: Callable, name: Optional[str] = None, description: Optional[str] = None) -> FunctionTool:
       """Convert a function to an ADK-compatible FunctionTool."""
       # Implementation...
   ```

## MCP Parent Init Fix

### Issue

After code restructuring, imports in the parent `__init__.py` files were no longer exporting the necessary components:

```
ImportError: cannot import name 'create_fileserver_toolset' from 'radbot.tools.mcp'
```

### Root Cause

The `__init__.py` files in the package hierarchy were not properly re-exporting symbols from submodules after the restructuring.

### Solution

Updated each `__init__.py` file to properly import and re-export all public symbols:

```python
# radbot/tools/mcp/__init__.py
from radbot.tools.mcp.mcp_fileserver_client import create_fileserver_toolset, test_fileserver_connection
from radbot.tools.mcp.mcp_tools import get_available_mcp_tools
from radbot.tools.mcp.mcp_utils import convert_to_adk_tool

__all__ = [
    'create_fileserver_toolset',
    'test_fileserver_connection',
    'get_available_mcp_tools',
    'convert_to_adk_tool',
]
```

## MCP Relative Imports Fix

### Issue

After restructuring, some modules were using relative imports but imports were failing:

```
ImportError: attempted relative import beyond top-level package
```

### Root Cause

Modules were trying to use relative imports like `from ...tools import X` but the package structure had changed, making these imports invalid.

### Solution

1. **Changed relative imports to absolute imports**:
   ```python
   # Before
   from ...config import config_manager
   
   # After
   from radbot.config import config_manager
   ```

2. **Updated import paths to match new structure**:
   ```python
   # Before
   from ..tools.memory_tools import search_past_conversations
   
   # After
   from radbot.tools.memory.memory_tools import search_past_conversations
   ```

## Agent Transfer Fix

### Issue

Agent transfers from `beto` to `scout` and back were failing with errors:

```
Malformed function call: transfer_to_agent
Agent 'beto' not found in the agent tree
```

### Root Causes

1. **Name Inconsistency**: The `app_name` parameter was inconsistent across the codebase
2. **Missing Bidirectional References**: Sub-agents were not properly linked to parent agents
3. **Missing Transfer Tool**: The `transfer_to_agent` tool was missing in some agents

### Solutions

1. **Standardized `app_name` Parameter**:
   ```python
   # Ensure consistent app_name across all agent creation
   agent = create_agent(app_name="beto")
   research_agent = create_research_agent(app_name="beto")
   ```

2. **Explicit Name Verification**:
   ```python
   # Force agent name consistency
   if hasattr(agent, 'name') and agent.name != 'beto':
       logger.warning(f"CRITICAL FIX: Root agent name mismatch: '{agent.name}' not 'beto', fixing...")
       agent.name = 'beto'
   ```

3. **Proper Bidirectional References**:
   ```python
   # Setup bidirectional relationship
   agent.sub_agents = []
   agent.sub_agents.append(research_agent)
   
   # Ensure parent reference (handle both attribute possibilities)
   if hasattr(research_agent, '_parent'):
       research_agent._parent = agent
   if hasattr(research_agent, 'parent'):
       research_agent.parent = agent
   ```

4. **Added Missing Transfer Tool**:
   ```python
   # Add transfer tools if missing
   if not root_has_transfer_tool:
       agent.tools.append(transfer_to_agent)
   
   if not scout_has_transfer_tool:
       research_agent.tools.append(transfer_to_agent)
   ```

5. **Detailed Debug Logging**:
   ```python
   logger.info(f"====== DETAILED AGENT TREE STRUCTURE =======")
   logger.info(f"ROOT AGENT NAME: '{agent.name}'")
   logger.info(f"SUB-AGENT NAME: '{research_agent.name}'")
   logger.info(f"PARENT REFERENCE: {research_agent.parent is agent if hasattr(research_agent, 'parent') else 'None'}")
   logger.info(f"SUB_AGENTS LIST: {agent.name in [sa.name for sa in agent.sub_agents if hasattr(sa, 'name')]}")
   logger.info(f"BIDIRECTIONAL RELATIONSHIP CHECK: {research_agent.parent is agent if hasattr(research_agent, 'parent') else False}")
   ```

## Agent UUID Fix

### Issue

The Agent UUID assignment in the web app was inconsistent, causing issues with conversation history and agent transfers.

### Root Cause

The RadBotAgent class was using a different UUID each time an agent was created, even though it was meant to represent the same agent.

### Solution

1. **Fixed UUID Generation**:
   ```python
   # Before
   self.uuid = uuid.uuid4()
   
   # After
   # Use a deterministic UUID based on the agent name
   self.uuid = uuid.uuid5(uuid.NAMESPACE_DNS, f"agent.{name}")
   ```

2. **Consistent App Name**:
   ```python
   # Use the same app_name throughout the codebase
   app_name = "beto"
   ```

## Key Lessons Learned

1. **Event Loop Management**: Be extremely careful when mixing async code with threading
2. **Consistent Naming**: Keep class and function names consistent across modules
3. **Explicit Parameters**: Always be explicit about `app_name` and other critical parameters
4. **Thorough Testing**: Test in both CLI and web environments to catch context-specific issues
5. **Defensive Programming**: Add fallbacks and detailed error handling
6. **Complete Refactoring**: When restructuring code, ensure all dependencies are updated
7. **Bidirectional References**: When using object hierarchies, maintain proper bidirectional references
8. **API Compatibility**: Be aware of MCP and ADK API changes between versions
9. **Detailed Logging**: Add comprehensive logging for debugging complex issues
10. **Simplification**: Sometimes a simpler approach (like tool stubs) is better than complex async solutions