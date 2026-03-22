# RadBot Spec

## Quick Ref
- Stack: Google ADK 1.27.2 | FastAPI | React 18 | PostgreSQL | Qdrant | MCP
- Entry: `python -m radbot.web` (web) | `python -m radbot` (CLI)
- Pkg: uv — always `uv run`
- Main agent: beto (90s SoCal personality, pure orchestrator)

## Specs
| Domain | File | Covers |
|--------|------|--------|
| Agents | specs/agents.md | beto routing, sub-agents, tool assignments, memory scoping |
| Tools | specs/tools.md | FunctionTool modules, MCP, tool patterns |
| Web | specs/web.md | FastAPI, React SPA, API routes, WS protocol |
| Storage | specs/storage.md | PostgreSQL tables, Qdrant, credential store |
| Integrations | specs/integrations.md | HA, Overseerr, Picnic, Jira, Gmail, ntfy, Ollama, GitHub |
| Config | specs/config.md | cfg system, priority chain, admin UI, hot-reload |
| Deployment | specs/deployment.md | Docker, Nomad, CI/CD, env vars |

## Cross-Cutting

<!-- Doc-keeper: expand with config priority, error patterns, logging format -->
