"""Self-service Claude Code bootstrap endpoint.

`GET /setup/claude-code.md` returns a markdown guide that tells Claude Code
how to configure itself against this radbot deployment. Unauthenticated so
it can be fetched on a fresh machine before the user has any token set.

The `base_url` is derived from the request so the same endpoint renders
correctly for dev (`http://localhost:8000`) and prod
(`https://radbot.demonsafe.com`).
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

router = APIRouter(prefix="/setup", tags=["setup"])


_TEMPLATE = """# Configure Claude Code for radbot

**Target radbot:** `{base_url}`

You're reading this because someone pointed Claude Code at
`{base_url}/setup/claude-code.md` and asked to be configured. Walk through
the steps below, asking for confirmation before editing any files.

---

## 1. Get the MCP token

The token lives in the operator's deployment secrets (Nomad env var
`RADBOT_MCP_TOKEN`). Ask the user to paste it, then help them persist it:

```bash
# Add to ~/.zshrc or ~/.bashrc
export RADBOT_MCP_TOKEN="<paste>"
export RADBOT_URL="{base_url}"
```

Have them `source` their profile before continuing.

## 2. Add the MCP server to ~/.claude/settings.json

Merge the following into the existing settings (do **not** overwrite the
whole file — read it first, merge the `mcpServers` key):

```json
{{
  "mcpServers": {{
    "radbot": {{
      "type": "http",
      "url": "{base_url}/mcp/sse",
      "headers": {{
        "Authorization": "Bearer ${{RADBOT_MCP_TOKEN}}"
      }}
    }}
  }}
}}
```

## 3. Install the `SessionStart` hook

Create `~/.claude/hooks/radbot-project-context.sh`:

```bash
#!/usr/bin/env bash
# Fetches per-project context from radbot when cwd matches a registered project.
# Silent on unknown paths so it's safe to leave installed on every machine.
set -euo pipefail

: "${{RADBOT_URL:={base_url}}}"
[ -z "${{RADBOT_MCP_TOKEN:-}}" ] && exit 0

project=$(curl -sf \\
  -H "Authorization: Bearer $RADBOT_MCP_TOKEN" \\
  "$RADBOT_URL/api/projects/match?cwd=$PWD" \\
  | jq -r '.project // empty' 2>/dev/null) || exit 0

[ -z "$project" ] && exit 0

curl -sf \\
  -H "Authorization: Bearer $RADBOT_MCP_TOKEN" \\
  "$RADBOT_URL/api/projects/$project/context.md"
```

Make it executable: `chmod +x ~/.claude/hooks/radbot-project-context.sh`

Then merge into `~/.claude/settings.json`:

```json
{{
  "hooks": {{
    "SessionStart": [
      {{"type": "command", "command": "~/.claude/hooks/radbot-project-context.sh"}}
    ]
  }}
}}
```

## 4. (Optional) Mount the ai-intel wiki locally

If the user has SMB access to the shared mount, add to their shell profile:

```bash
export AI_INTEL_MOUNT="/run/user/$(id -u)/gvfs/smb-share:server=beefcake.local,share=share/ai-intel"
```

Without this, the `llm-wiki:*` skills still work via radbot's MCP
`wiki_*` tools — they just go over the network instead of the filesystem.

## 5. Install the `/park` and `/resume` skills

Preferred: from the `perrymanuk/claude-skills` marketplace (likely already
in `~/.claude/settings.json` under `extraKnownMarketplaces`):

> "Install the park and resume skills from the claude-skills marketplace."

Manual fallback:

```bash
git clone git@github.com:perrymanuk/claude-skills.git ~/.claude/skills-src
ln -s ~/.claude/skills-src/park ~/.claude/skills/park
ln -s ~/.claude/skills-src/resume ~/.claude/skills/resume
```

## 6. Verify

Start a new Claude Code session and ask:

> What does radbot say my full Telos contains?

Expected: Claude calls `telos_get_full` via the radbot MCP server and
summarizes the user's mission / goals / projects. If instead Claude says
the tool isn't available, check that the CLI was restarted after the
settings edit.

## Troubleshooting

- **401 Unauthorized**: token missing or stale. Re-export and restart.
- **503 MCP bridge disabled**: server is running but `RADBOT_MCP_TOKEN` is
  unset in radbot's deployment env. Operator needs to set it and redeploy.
- **No SessionStart context**: cwd doesn't match any registered radbot
  project. Register it:
  `project_register(name="myproj", path_patterns=["/git/myorg/myproj"])`
  via the radbot MCP.
- **Skill not found**: skills are scanned at CLI startup. Restart Claude
  Code after adding them.
"""


@router.get("/claude-code.md", response_class=PlainTextResponse)
async def claude_code_setup(request: Request) -> str:
    """Render the Claude Code setup guide with this deployment's base URL."""
    base_url = str(request.base_url).rstrip("/")
    return _TEMPLATE.format(base_url=base_url)
