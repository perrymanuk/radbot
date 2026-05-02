# Claude Code MCP config migration — PT109

PT109 retired the radbot MCP bridge's SSE transport and replaced it with
the modern streamable-HTTP transport in **stateless mode** at a single
endpoint: `POST /mcp`. Every machine that had Claude Code (or any other
MCP client) talking to radbot needs its `mcpServers` config updated.

## Why this changes

The old SSE transport (`GET /mcp/sse` + `POST /mcp/messages/`) kept a
per-client session in process memory on the radbot server. Any time the
radbot process restarted — Nomad health-check restart, a deploy, OOM —
every existing session UUID became invalid, and the next POST hit 404
("Could not find session"). The user-visible symptom was Claude Code
saying it couldn't find tools mid-session, requiring `/mcp` to fully
reconnect.

Streamable-HTTP stateless mode has **no shared session state**. Each
request to `/mcp` constructs a fresh `StreamableHTTPServerTransport`,
runs the JSON-RPC, and tears it down. There is no dict to fall out of
sync with the client, so process restarts are invisible.

## Migration on each client machine

### 1. Edit `~/.claude.json`

Find the `radbot` entry under `mcpServers`. It should currently look
something like:

```json
{
  "mcpServers": {
    "radbot": {
      "type": "sse",
      "url": "https://radbot.demonsafe.com/mcp/sse",
      "headers": {
        "Authorization": "Bearer <token>"
      }
    }
  }
}
```

Change `type` to `http` and drop `/sse` from the URL:

```json
{
  "mcpServers": {
    "radbot": {
      "type": "http",
      "url": "https://radbot.demonsafe.com/mcp",
      "headers": {
        "Authorization": "Bearer <token>"
      }
    }
  }
}
```

Two changes:

- `"type": "sse"` → `"type": "http"`
- `"url": ".../mcp/sse"` → `"url": ".../mcp"` (no trailing path, no
  trailing slash)

The bearer token is unchanged. If you can't remember where it lives, the
admin UI's "MCP Bridge" panel can reveal or rotate it.

### 2. Reload Claude Code

Either restart the CLI, or run `/mcp` to force a reconnect against the
new endpoint. The first tool call should succeed; if it 404s or times
out, double-check the URL doesn't still have `/sse` on the end.

### 3. Verify

Ask Claude Code to call any radbot tool, e.g.:

```
What does radbot say my full Telos contains?
```

You should see a normal `telos_get_full` result. If the response is
"that tool isn't available," restart the CLI — schema discovery happens
on connect.

## Local dev

For local dev at `http://localhost:8000`, the same change applies — the
URL becomes `http://localhost:8000/mcp` with `"type": "http"`.

## Rolling back

If you need to roll back (you shouldn't — the SSE transport is gone
server-side), the `git revert` of the PT109 PR restores `mount_mcp_on_app`
to the SSE-based version and brings `/mcp/sse` + `/mcp/messages/` back.
Then revert each client's `~/.claude.json` to `"type": "sse"` /
`/mcp/sse`. Don't operate in a half-rolled-back state — clients pointed
at `/mcp/sse` against a streamable-HTTP-only server will 404.

## Related

- `docs/implementation/mcp_bridge.md` — overall MCP bridge architecture
- `radbot/mcp_server/http_transport.py` — server-side transport definition
- `GET /setup/claude-code.md` (rendered live by the deployment) — the
  templated bootstrap doc for new machines, already updated to the new URL
