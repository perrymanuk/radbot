# Webhooks

Webhooks allow external services to trigger agent actions by POSTing JSON to an endpoint. The payload is rendered into a prompt template, sent to the agent, and the response is pushed to all connected web UI clients.

## Architecture

- **Storage**: PostgreSQL `webhook_definitions` table (same DB as todos)
- **Template Engine**: `{{payload.key.subkey}}` dot-notation substitution
- **Security**: Optional HMAC-SHA256 signature validation
- **API**: REST endpoints at `/api/webhooks`

## Agent Tools

The agent has three webhook tools:

### `create_webhook`
Register a new webhook endpoint.

Parameters:
- `name` (str, required): Human-readable name
- `path_suffix` (str, required): URL path suffix (e.g., `github-push` creates `/api/webhooks/trigger/github-push`)
- `prompt_template` (str, required): Template with `{{payload.key}}` placeholders
- `secret` (str, optional): Shared secret for HMAC-SHA256 validation

Example conversation:
```
User: Create a webhook for GitHub push events
Agent: [calls create_webhook with
        name="GitHub Push",
        path_suffix="github-push",
        prompt_template="A push was made to {{payload.repository.full_name}} by {{payload.pusher.name}} with message: {{payload.head_commit.message}}. Summarize this update.",
        secret="my-webhook-secret"]
```

### `list_webhooks`
List all registered webhooks with their trigger URL and count.

### `delete_webhook`
Delete a webhook by its ID.

Parameters:
- `webhook_id` (str, required): UUID of the webhook to delete

## Template Syntax

Templates use `{{path}}` syntax with dot-notation for nested JSON access:

| Template | Payload | Result |
|----------|---------|--------|
| `{{payload.user.name}}` | `{"user": {"name": "Perry"}}` | `Perry` |
| `{{payload.items.0.title}}` | `{"items": [{"title": "First"}]}` | `First` |
| `{{payload.repo}}` | `{"repo": "radbot"}` | `radbot` |

Unresolved placeholders are left as-is (e.g., `{{payload.missing}}` stays in the output).

## Triggering a Webhook

External services POST JSON to the trigger endpoint:

```bash
# Without secret
curl -X POST http://localhost:8000/api/webhooks/trigger/github-push \
  -H "Content-Type: application/json" \
  -d '{"repository": {"full_name": "user/repo"}, "pusher": {"name": "perry"}, "head_commit": {"message": "fix: bug"}}'

# With HMAC secret
PAYLOAD='{"event": "deploy", "status": "success"}'
SIGNATURE=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "my-webhook-secret" | awk '{print $2}')
curl -X POST http://localhost:8000/api/webhooks/trigger/my-webhook \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Signature: sha256=$SIGNATURE" \
  -d "$PAYLOAD"
```

## REST API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/webhooks/definitions` | List all webhooks |
| POST | `/api/webhooks/definitions` | Create a new webhook |
| DELETE | `/api/webhooks/definitions/{webhook_id}` | Delete a webhook |
| POST | `/api/webhooks/trigger/{path_suffix}` | Trigger a webhook (external use) |

## How It Works

1. Agent creates a webhook via the `create_webhook` tool
2. Webhook definition is stored in PostgreSQL
3. External service POSTs JSON to `/api/webhooks/trigger/{path_suffix}`
4. Server validates HMAC signature (if secret is configured)
5. Payload is rendered into the prompt template
6. Rendered prompt is sent to the agent
7. Agent's response is broadcast to all WebSocket clients
8. Response appears in web UI as a message from "WEBHOOK"
9. HTTP caller receives `{"status": "accepted"}` immediately (processing is async)

## Configuration

In `config.yaml`:
```yaml
webhooks:
  enabled: true
  max_payload_size: 65536
```

## Database Schema

```sql
CREATE TABLE IF NOT EXISTS webhook_definitions (
    webhook_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    path_suffix TEXT NOT NULL UNIQUE,
    prompt_template TEXT NOT NULL,
    secret TEXT,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    last_triggered_at TIMESTAMPTZ,
    trigger_count INTEGER NOT NULL DEFAULT 0,
    metadata JSONB
);
```

## Files

| File | Purpose |
|------|---------|
| `radbot/tools/webhooks/__init__.py` | Package exports |
| `radbot/tools/webhooks/db.py` | Database schema + CRUD |
| `radbot/tools/webhooks/webhook_tools.py` | Agent tool functions |
| `radbot/tools/webhooks/template_renderer.py` | `{{path}}` template engine |
| `radbot/web/api/webhooks.py` | REST API router + trigger endpoint |
