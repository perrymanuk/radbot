# Ollama Support

RadBot supports running agents on local Ollama-hosted LLMs via ADK's built-in
`LiteLlm` integration. This enables fully local inference with no cloud
dependency.

## How It Works

`ConfigManager.resolve_model()` detects Ollama model strings (prefixed with
`ollama_chat/` or `ollama/`) and wraps them in ADK's `LiteLlm` class with the
configured `api_base`. Gemini model strings pass through unchanged.

All agent factories and the hot-reload path call `resolve_model()`, so switching
between Gemini and Ollama is a config change — no code changes required.

## Configuration

### Via Admin UI

1. Navigate to **Admin > Infrastructure > Ollama**
2. Set **API Base URL** to your Ollama server (e.g. `https://ollama.example.com`)
3. Optionally set an API key (for authenticated servers)
4. Click **Save** and **Test Connection**
5. Pull desired models from the panel
6. Navigate to **Admin > Core > Agent & Models**
7. Set agent models to `ollama_chat/<model-name>` (e.g. `ollama_chat/mistral-small3.2`)

### Via Environment Variables

```bash
OLLAMA_API_BASE=https://ollama.example.com
OLLAMA_API_KEY=optional-key       # only for authenticated servers
RADBOT_MAIN_MODEL=ollama_chat/mistral-small3.2
RADBOT_SUB_MODEL=ollama_chat/mistral-small3.2
```

### Via DB Config

Store in `config:integrations`:
```json
{
  "ollama": {
    "enabled": true,
    "api_base": "https://ollama.example.com",
    "api_key": null
  }
}
```

Store in `config:agent`:
```json
{
  "main_model": "ollama_chat/mistral-small3.2",
  "sub_agent_model": "ollama_chat/mistral-small3.2"
}
```

## Model String Format

Use `ollama_chat/<model>` (preferred) or `ollama/<model>`:

- `ollama_chat/mistral-small3.2` — Mistral Small 3.2 (24B)
- `ollama_chat/llama3.2` — Llama 3.2 (various sizes)
- `ollama_chat/qwen2.5:14b` — Qwen 2.5 14B

The `ollama_chat/` prefix uses the chat completion endpoint (recommended for
agents that need function calling).

## Recommended Models

For agentic use with tool/function calling:

| Model | Size | Notes |
|---|---|---|
| `mistral-small3.2` | 24B | Strong function calling, recommended |
| `qwen2.5:14b` | 14B | Good balance of size and capability |
| `llama3.2:latest` | 11B | Lighter weight option |

Hardware recommendation: Mac Mini M4 32GB+ or GPU with 24GB+ VRAM (e.g. RTX 3090)
for 24B models.

## Gemini-Only Features

Two agents use Gemini-specific capabilities that do NOT work with Ollama:

1. **search_agent** — Uses `google_search` grounding tool (Gemini-only). On
   Ollama, web search will not be available. Could be replaced with MCP-based
   search in the future.

2. **code_execution_agent** — Uses `BuiltInCodeExecutor` (Gemini-only). On
   Ollama, code execution won't work. The shell tool on the axel agent is an
   alternative.

These agents log clear warnings when configured with Ollama models but the
configuration is allowed — they simply won't function for their Gemini-specific
features.

## Architecture

```
ConfigManager.resolve_model(model_string)
    ├── starts with "ollama_chat/" or "ollama/"
    │   └── returns LiteLlm(model=..., api_base=...)
    └── otherwise
        └── returns model_string unchanged (Gemini path)
```

All agent factories call `resolve_model()`:
- `agent_core.py` (beto)
- `home_agent/factory.py` (casa)
- `planner_agent/factory.py` (planner)
- `tracker_agent/factory.py` (tracker)
- `comms_agent/factory.py` (comms)
- `execution_agent/factory.py` (axel)
- `research_agent/factory.py` + `agent.py` (scout)
- `search_tool.py` (search_agent)
- `code_execution_tool.py` (code_execution_agent)

Hot-reload via `apply_model_config()` also calls `resolve_model()`.

## Admin Client

`radbot/tools/ollama/ollama_client.py` provides a singleton HTTP client for
admin operations (listing, pulling, deleting models). It follows the same
pattern as `overseerr_client.py`.

Admin API endpoints:
- `POST /admin/api/test/ollama` — Test connectivity
- `GET /admin/api/ollama/models` — List downloaded models
- `POST /admin/api/ollama/pull` — Pull a model (600s timeout)
- `DELETE /admin/api/ollama/models/{name}` — Delete a model
