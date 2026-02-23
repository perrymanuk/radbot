# Claude Code + GitHub App Integration

Autonomous coding workflow that allows RadBot to clone repositories, plan changes with Claude Code CLI, iterate on plans with user feedback, execute approved changes, and push back to GitHub.

## Architecture

```
User → Beto → Axel (6 tools)
                  ├── clone_repository      → GitHubAppClient (JWT auth → clone)
                  ├── claude_code_plan      → ClaudeCodeClient (--print, read-only)
                  ├── claude_code_continue  → ClaudeCodeClient (--resume, iterate)
                  ├── claude_code_execute   → ClaudeCodeClient (--dangerously-skip-permissions)
                  ├── commit_and_push       → GitHubAppClient (git add/commit/push)
                  └── list_workspaces       → DB (coder_workspaces table)
```

## Components

### GitHub App Client (`radbot/tools/github/github_app_client.py`)

Singleton client following the `overseerr_client.py` pattern.

**Authentication flow:**
1. Generate RS256 JWT signed with the App's private key (10-min expiry)
2. Exchange JWT for an installation access token via GitHub API (1-hour expiry, auto-refreshed)
3. Use installation token for git clone/push operations

**Key class: `GitHubAppClient`**
- `_generate_jwt()` — RS256 JWT with `PyJWT[crypto]`
- `_get_installation_token()` — Cached, auto-refreshes before expiry
- `clone_repo(owner, repo, workspace_dir, branch)` — Clone or pull with `x-access-token`
- `push_changes(local_path, branch)` — Refresh token, update remote, push
- `get_status()` — Health check via `GET /app`

**Config:**
- `integrations.github.app_id` — GitHub App ID
- `integrations.github.installation_id` — Installation ID
- `github_app_private_key` — PEM key in credential store (encrypted)

### Claude Code Client (`radbot/tools/claude_code/claude_code_client.py`)

Async wrapper for the Claude Code CLI.

**Key design decisions:**
- `--print` mode (non-interactive) for all invocations
- `--output-format stream-json` for parseable streaming output
- `--resume <session_id>` for conversation continuity across calls
- Plan mode = no `--dangerously-skip-permissions` (effectively read-only)
- Execute mode = with `--dangerously-skip-permissions` (full write access)

**Key class: `ClaudeCodeClient`**
- `run_plan(working_dir, prompt, session_id)` — Read-only planning
- `run_execute(working_dir, prompt, session_id)` — Full execution
- `_run_process(cmd, working_dir)` — Async subprocess, stream-json parsing

**Auth:** `CLAUDE_CODE_OAUTH_TOKEN` env var or `claude_code_oauth_token` in credential store.

### Agent Tools (`radbot/tools/claude_code/claude_code_tools.py`)

Six `FunctionTool` wrappers added to the axel agent:

| Tool | Purpose | Key Args |
|------|---------|----------|
| `clone_repository` | Clone/update repo via GitHub App | `owner`, `repo`, `branch` |
| `claude_code_plan` | Run Claude Code in plan mode | `prompt`, `work_folder`, `session_id` |
| `claude_code_continue` | Resume session with feedback | `prompt`, `session_id`, `work_folder` |
| `claude_code_execute` | Execute with skip-permissions | `prompt`, `work_folder`, `session_id` |
| `commit_and_push` | Stage, commit, push via GitHub App | `work_folder`, `commit_message`, `branch` |
| `list_workspaces` | List cloned repo workspaces | (none) |

### Database (`radbot/tools/claude_code/db.py`)

**Table: `coder_workspaces`**
```sql
CREATE TABLE coder_workspaces (
    workspace_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner TEXT NOT NULL,
    repo TEXT NOT NULL,
    branch TEXT NOT NULL DEFAULT 'main',
    local_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    last_session_id TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(owner, repo, branch)
);
```

The `last_session_id` enables `--resume` across different chat sessions.

## Workflow

```
1. clone_repository("perrymanuk", "radbot")
   → GitHubAppClient clones repo → /app/workspaces/perrymanuk/radbot
   → Returns work_folder

2. claude_code_plan("Add a /healthz endpoint", work_folder)
   → Claude Code reads codebase, generates plan
   → Returns plan text + session_id

3. User reviews plan, provides feedback

4. claude_code_continue("Use /health instead", session_id, work_folder)
   → Claude Code resumes conversation (--resume), updates plan
   → Returns updated plan

5. User approves

6. claude_code_execute("Execute the plan", work_folder, session_id)
   → Claude Code runs with --dangerously-skip-permissions
   → Files are modified in workspace

7. commit_and_push(work_folder, "feat: add health endpoint", "feature/health")
   → git add, commit, push using GitHub App token
```

## Admin UI

Two panels under Developer group in `/admin`:

**GitHub App Panel** (`DeveloperPanels.tsx`):
- App ID, Installation ID, Private Key (textarea), Enabled toggle
- Test button → `POST /api/test/github`

**Claude Code Panel** (`DeveloperPanels.tsx`):
- OAuth Token (password field), Workspace Directory
- Test button → `POST /api/test/claude-code`

## Setup

1. **Create a GitHub App** at github.com/settings/apps/new
   - Permissions: Contents (R/W), Pull Requests (R/W), Metadata (R)
   - Install on desired repos
   - Note App ID, generate private key, note Installation ID

2. **Generate Claude Code token**: Run `claude setup-token`

3. **Configure in Admin UI** (`/admin/`):
   - Developer > GitHub App: App ID, Installation ID, paste PEM private key
   - Developer > Claude Code: Paste OAuth token

4. **Docker image** must include Node.js 20 + Claude Code CLI (already in Dockerfile)

## Files

| File | Purpose |
|------|---------|
| `radbot/tools/github/__init__.py` | Package init |
| `radbot/tools/github/github_app_client.py` | GitHub App JWT auth, clone, push |
| `radbot/tools/claude_code/__init__.py` | Package init |
| `radbot/tools/claude_code/claude_code_client.py` | Async Claude CLI wrapper |
| `radbot/tools/claude_code/claude_code_tools.py` | 6 FunctionTool wrappers |
| `radbot/tools/claude_code/db.py` | Schema + CRUD for workspaces |
| `radbot/web/frontend/src/components/admin/panels/DeveloperPanels.tsx` | Admin panels |

## Relation to Legacy Claude CLI Integration

The older MCP-based Claude CLI integration (`radbot/tools/mcp/direct_claude_cli.py`, documented in `claude-cli.md` and `claude-prompt.md`) used Claude as an MCP server for shell commands and prompting. The new Claude Code integration is a separate, higher-level workflow that uses Claude Code CLI directly as an autonomous coding agent with session persistence and GitHub App authentication. Both can coexist — the MCP integration serves a different purpose (ad-hoc commands) than the Code integration (full coding workflow).
