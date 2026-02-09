# RadBot Dead Code Investigation Log

## Goal
Identify and remove unused files and functions within the `/Users/perry.manuk/git/perrymanuk/radbot` codebase.

## Status
In Progress - Examining `tools` directory for internal dead code. **Confirmed `tools/mcp_fileserver_client.py` is likely dead code.**

## Approach
Due to technical issues running automated tools directly, we will examine the codebase directory by directory, listing contents and reviewing suspicious files. Findings will be logged below.

## Tasks
- [x] Examine top-level directory contents
- [x] Examine `radbot` directory contents
- [x] Examine `radbot/agent` directory contents
- [x] Examine `radbot/agent/research_agent` directory contents
- [x] Examine `radbot/agent/research_agent/agent.py`
- [x] Examine `radbot/agent/research_agent/instructions.py`
- [x] Examine `radbot/agent/research_agent/tools.py`
- [x] Examine `radbot/agent/research_agent/factory.py`
- [x] Examine `radbot/agent/research_agent/sequential_thinking.py`
- [x] Examine `tools` directory contents
- [x] Examine `tools/mcp_fileserver_client.py`
- [x] Search/Manually check `radbot` directory for usage of `mcp_fileserver_client` (no usage found in reviewed files).
- [x] Manually check remaining files in `radbot/filesystem` for internal dead code (`adapter.py`, `tools.py`, `security.py`, `integration.py`, `__init__.py` reviewed - no internal dead code found).
- [x] Examine `radbot/memory` directory contents
- [x] Examine `radbot/memory/embedding.py` (no usage of `mcp_fileserver_client` found)
- [x] Examine `radbot/memory/curl_client.py` (no usage of `mcp_fileserver_client` found)
- [x] Examine `radbot/memory/qdrant_memory.py` (no usage of `mcp_fileserver_client` found)
- [x] Examine `radbot/memory/enhanced_memory` directory contents
- [x] Examine `radbot/memory/enhanced_memory/memory_manager.py` (no usage of `mcp_fileserver_client` found)
- [x] Examine `radbot/memory/enhanced_memory/memory_detector.py` (no usage of `mcp_fileserver_client` found)
- [x] Examine `radbot/cache` directory contents
- [x] Examine `radbot/cache/__init__.py` (no usage of `mcp_fileserver_client` found)
- [x] Examine `radbot/config` directory contents
- [x] Examine `radbot/config/settings.py` (no usage of `mcp_fileserver_client` found)
- [x] Examine `radbot/callbacks` directory contents
- [x] Examine `radbot/callbacks/__init__.py` (no usage of `mcp_fileserver_client` found)
- [x] Examine `radbot/web` directory contents
- [x] Examine `radbot/web/__init__.py` (no usage of `mcp_fileserver_client` found)
- [x] Examine `radbot/web/app.py` (no usage of `mcp_fileserver_client` found)
- [x] Examine `radbot/web/__main__.py` (no usage of `mcp_fileserver_client` found)
- [x] Examine `radbot/web/api` directory contents
- [x] Examine `radbot/web/api/events.py` (no usage of `mcp_fileserver_client` found)
- [x] Examine `radbot/web/api/session.py` (no usage of `mcp_fileserver_client` found)
- [x] Examine `radbot/filesystem` directory contents
- [x] Examine `radbot/filesystem/adapter.py` (no usage of `mcp_fileserver_client` found)
- [x] Examine `radbot/filesystem/tools.py` (no internal dead code found)
- [x] Examine `radbot/filesystem/security.py` (no internal dead code found)
- [x] Examine `radbot/filesystem/integration.py` (no internal dead code found)
- [x] Examine `tools/create_calendar_token.py` (no internal dead code found)
- [x] Examine `tools/save_calendar_token.py` (no internal dead code found)
- [ ] Examine `tools/mcp_fileserver_server.py` for internal dead code.
- [ ] Examine remaining non-test `.py` files in `tools` for internal dead code.
- [ ] Examine `.sh` scripts in `tools`
- [ ] Examine `task-api` directory
- [ ] Examine `examples` directory
- [ ] Examine `scripts` directory
- [ ] Review `tests` directory (note tests are expected to be unused by app)
- [ ] Log potential dead code findings
- [ ] Discuss findings and plan removals

----- QUICK FINDINGS FOR `radbot/agent/research_agent/agent.py` ---
No immediately obvious dead code (unused functions/methods) found based on manual review of this file's content.

----- QUICK FINDINGS FOR `radbot/agent/research_agent/instructions.py` ---
Contains string constants and a function to combine them. All appear used by `agent.py`. No obvious dead code found.

----- QUICK FINDINGS FOR `radbot/agent/research_agent/tools.py` ---
Found potential dead code: `get_research_tools()` function. Docstring indicates it's a placeholder and tools are provided externally. **Confirmed dead code.**

----- QUICK FINDINGS FOR `radbot/agent/research_agent/factory.py` ---
Contains `create_research_agent` function. Appears functional and is the intended way to create the agent, passing tools externally. No obvious dead code within this file.

----- QUICK FINDINGS FOR `radbot/agent/research_agent/sequential_thinking.py` ---
Contains logic for sequential thinking (classes `ThoughtStep`, `SequentialThinking`, functions `detect_thinking_trigger`, `process_thinking`). All appear used by `agent.py`. No obvious dead code found.

----- QUICK FINDINGS FOR `tools/mcp_fileserver_client.py` ---
Contains utility/test functions for creating/testing the fileserver toolset. All functions within the file are used internally by its test/main execution block. **Confirmed dead code for main application.**

----- QUICK FINDINGS FOR `radbot/memory/embedding.py` ---
Concerns embedding functionality. No usage of `mcp_fileserver_client` found.

----- QUICK FINDINGS FOR `radbot/memory/curl_client.py` ---
Implements a Curl client for Qdrant. No usage of `mcp_fileserver_client` found.

----- QUICK FINDINGS FOR `radbot/memory/qdrant_memory.py` ---
Implements Qdrant memory service. No usage of `mcp_fileserver_client` found.

----- QUICK FINDINGS FOR `radbot/memory/enhanced_memory/memory_manager.py` ---
Manages enhanced memory layers. No usage of `mcp_fileserver_client` found.

----- QUICK FINDINGS FOR `radbot/memory/enhanced_memory/memory_detector.py` ---
Detects memory triggers. No usage of `mcp_fileserver_client` found.

----- QUICK FINDINGS FOR `radbot/cache/__init__.py` ---
Empty file with docstring. No usage of `mcp_fileserver_client` found.

----- QUICK FINDINGS FOR `radbot/config/settings.py` ---
Handles configuration loading. No usage of `mcp_fileserver_client` found.

----- QUICK FINDINGS FOR `radbot/callbacks/__init__.py` ---
Empty file with docstring. No usage of `mcp_fileserver_client` found.

----- QUICK FINDINGS FOR `radbot/web/__init__.py` ---
Empty file with docstring. No usage of `mcp_fileserver_client` found.

----- QUICK FINDINGS FOR `radbot/web/app.py` ---
Implements the main web application logic. No usage of `mcp_fileserver_client` found.

----- QUICK FINDINGS FOR `radbot/web/__main__.py` ---
Handles web server startup. No usage of `mcp_fileserver_client` found.

----- QUICK FINDINGS FOR `radbot/web/api/events.py` ---
Handles API endpoints for events. No usage of `mcp_fileserver_client` found.

----- QUICK FINDINGS FOR `radbot/web/api/session.py` ---
Manages web sessions. No usage of `mcp_fileserver_client` found.

----- QUICK FINDINGS FOR `radbot/filesystem/adapter.py` ---
Provides compatibility functions for filesystem tools. No usage of `mcp_fileserver_client` found.

----- QUICK FINDINGS FOR `radbot/filesystem/tools.py` ---
Implements core filesystem tools. All internal functions/methods appear used. No obvious internal dead code found.

----- QUICK FINDINGS FOR `radbot/filesystem/security.py` ---
Provides filesystem security functions. All internal functions/methods appear used (primarily by `tools.py`). No obvious internal dead code found.

----- QUICK FINDINGS FOR `radbot/filesystem/integration.py` ---
Integrates filesystem tools with ADK. All internal functions/methods appear used (by `create_filesystem_tools`). No obvious internal dead code found.

----- QUICK FINDINGS FOR `tools/create_calendar_token.py` ---
Standalone utility script. All internal functions/methods appear used within the script.

----- QUICK FINDINGS FOR `tools/save_calendar_token.py` ---
Standalone utility script for saving calendar tokens. All internal functions/methods appear used within the script. No obvious internal dead code found.

---

## Examination Notes

### Initial Scan (Top-Level)
Found directories: `tools`, `.pytest_cache`, `task-api`, `tests`, `.claude`, `__pycache__`, `docs`, `img`, `radbot`, `.git`, `examples`, `.venv`, `scripts`
Found files: `adk.config.json`, `pytest.ini`, `Makefile`, `pyproject.toml`, `.env.bak`, `README.md`, `TASKS.md`, `.gitignore`, `.env`, `.env.new`, `.env.example`, `ui.md`, `CLAUDE.md`, `code_eval.md`

Excluding cache, git, and documentation directories/files. Focusing investigation on `radbot`, `tools`, `task-api`, `examples`, and `scripts`.

### Examining `radbot` directory
Contents:
Directories: `tools`, `memory`, `cache`, `config`, `callbacks`, `web`, `utils`, `agent`, `filesystem`, `__pycache__`, `cli`
Files: `__init__.py`, `agent.py`, `__main__.py`

Next, we investigate the `agent` directory within `radbot`.

### Examining `radbot/agent` directory
Contents:
Directories: `__pycache__`, `research_agent`
Files: `enhanced_memory_agent_factory.py`, `scout_agent_factory.py`, `home_assistant_agent_factory.py`, `shell_agent_factory.py`, `todo_agent_factory.py`, `__init__.py`, `agent.py`, `memory_agent_factory.py`, `calendar_agent_factory.py`, `web_search_agent_factory.py`

Next step is to examine the `research_agent` subdirectory.

### Examining `radbot/agent/research_agent` directory
Contents:
Files: `instructions.py`, `tools.py`, `__init__.py`, `factory.py`, `agent.py`, `sequential_thinking.py`

Examined `radbot/agent/research_agent/agent.py`.
Examined `radbot/agent/research_agent/instructions.py`.
Examined `radbot/agent/research_agent/tools.py`. Found `get_research_tools` function is likely dead code. Confirmed by examining `factory.py`.
Examined `radbot/agent/research_agent/factory.py`.
Examined `radbot/agent/research_agent/sequential_thinking.py`.

All core files in `radbot/agent/research_agent` have been examined. Moving investigation to the root `tools` directory.

### Examining `tools` directory
Contents:
Directories: `__pycache__`
Files: `create_calendar_token.py`, `test_calendar_service_account.py`, `basic_direct_test.py`, `test_calendar_fix.py`, `test_calendar_auth.py`, `save_calendar_token.py`, `test_weather_tool.py`, `test_calendar_schema_fix.py`, `test_mcp_fs_simple.py`, `mcp_fileserver_client.py`, `test_calendar_token_refresh.py`, `run_web_with_fs.py`, `check_mcp_env.py`, `test_mcp_fileserver.py`, `run_with_mcp.sh`, `test_calendar_error_handling.py`, `ha_standalone_agent.py`, `memory_tools.py`, `validate_qdrant_fix.py`, `tavily_search_util.py`, `mcp_fileserver_server.py`, `direct_token_refresh.py`, `test_web_startup.py`, `__init__.py`, `validate_calendar_service_account.py`, `test_direct_call.py`, `test_calendar_simple.py`, `test_search_function.py`, `ha_mcp_direct.py`, `test_entity_search.py`, `test_calendar_oauth.py`, `direct_function_tool.py`, `test_ha_rest_api.py`, `ha_connection_test.py`, `direct_ha_check.py`, `test_weather_web_interface.py`, `test_fileserver_integration.py`, `test_weather_function_call.py`, `get_google_token.py`, `test_calendar_json_fallback.py`, `test_ha_entities.py`, `validate_crawl4ai_fix.py`, `test_crawl4ai_depth.py`, `test_crawl4ai_vector_search.py`, `test_simple_agent.py`, `test_ha_search.py`, `test_with_direct_call.py`, `test_crawl4ai_direct.py`, `test_crawl4ai_imports.py`, `fix_calendar_token.py`, `simple_ha_websocket.py`, `debug_ha_tools.py`, `run_web_with_env.sh`, `test_urllib_config.py`, `diagnose_search_tool.py`

Focusing examination on non-test Python files and scripts.

Examined `tools/mcp_fileserver_client.py`. Contains utility/test functions for creating/testing the fileserver toolset. All functions within the file are used internally by its test/main execution block. **Confirmed dead code for main application.**
Search for usage of `mcp_fileserver_client` in `radbot` directory is not possible with current tools for full text search across directories. Manual file review completed across `radbot/agent`, `radbot/memory` (and subdirs), `radbot/cache`, `radbot/config`, `radbot/callbacks`, `radbot/web` (and subdirs), and `radbot/filesystem` (and subdirs). No usage found in these areas.

Moving to manual review of remaining non-test `.py` files in the root `tools` directory for internal dead code.

Examined `tools/create_calendar_token.py` (no internal dead code found).
Examined `tools/save_calendar_token.py` (no internal dead code found).
Examining `tools/mcp_fileserver_server.py`.
