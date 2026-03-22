# Deployment

## Production

- **Endpoint**: `https://radbot.demonsafe.com`
- **Nomad job**: `~/git/perrymanuk/hashi-homelab/nomad_jobs/ai-ml/radbot/nomad.job`
- **Docker image**: `ghcr.io/perrymanuk/radbot` — auto-built by `.github/workflows/docker-build.yml` on push to `main`
- **Versioning**: Auto-incremented `v{MAJOR}.{BUILD}` tags (e.g. `v0.14`). Update the `image` tag in the Nomad job after pushing.
- **Reverse proxy**: Traefik via Consul service discovery. `ProxyHeadersMiddleware` handles `X-Forwarded-Proto`.

## Bootstrap Config

Nomad templates a minimal `config.yaml` with only `database:` section. All other config loaded from DB credential store at startup.

| Env var | Purpose |
|---------|---------|
| `RADBOT_CREDENTIAL_KEY` | Fernet key for encrypted credentials in DB |
| `RADBOT_ADMIN_TOKEN` | Bearer token for `/admin/` API |
| `RADBOT_CONFIG_FILE` | Path to `config.yaml` (default: auto-discovered) |
| `RADBOT_ENV` | `dev` loads `config.dev.yaml` instead of `config.yaml` |

## Main Nomad Job

```
type = "service", count = 1
image: ghcr.io/perrymanuk/radbot:{tag}
port: 8000 (HTTP), host_network = "lan"
constraint: shared_mount = true
service: "radbot" (Traefik-enabled)
health: GET /health every 30s
resources: cpu=1000, memory=2048
```

## Session Workers (Remote Mode)

When `config:agent` → `session_mode = "remote"`, each chat session runs as an independent Nomad batch job:

```
Browser ◄──WS──► Main radbot App (gateway)
                      │
                      │ A2A HTTP
                      ▼
                 Nomad Worker Job
                 (radbot-session-{id[:8]})
```

### Worker Job Spec

```
type = "batch" (no reschedule on exit — workers self-terminate on idle)
image: same as main app at spawn time
cmd: python -m radbot.worker --session-id <UUID> --port 8000 --idle-timeout 3600
port: dynamic (Nomad-assigned), host_network = "lan"
constraint: shared_mount = true
service: "radbot-session", tags: ["session_id=<UUID>"]
health: GET /health every 30s
resources: cpu=500, memory=1024
restart: attempts=1, mode=fail
```

### Worker Lifecycle

1. **Spawn**: `SessionProxy` submits Nomad batch job via `NomadClient.submit_job()`
2. **Discover**: Nomad service discovery (`/v1/service/radbot-session`) by `session_id` tag
3. **Health**: Poll `/health` until 200 (up to 120s timeout)
4. **Message**: A2A HTTP via `a2a-sdk` client → worker's `to_a2a()` endpoint
5. **Idle**: Worker self-terminates after `idle_timeout` seconds (default 3600) via SIGTERM
6. **Fallback**: If Nomad unreachable or worker limit reached, falls back to local `SessionRunner`

### Config

| Key | Location | Default | Purpose |
|-----|----------|---------|---------|
| `session_mode` | `config:agent` | `local` | `local` or `remote` |
| `max_session_workers` | `config:agent` | `10` | Concurrency cap |
| `worker_image_tag` | `config:agent` | env `RADBOT_WORKER_IMAGE_TAG` or `latest` | Docker tag for workers |

### Key Files

| File | Purpose |
|------|---------|
| `radbot/worker/__main__.py` | Worker entry point (A2A server + idle watchdog) |
| `radbot/worker/nomad_template.py` | Generates Nomad JSON job spec |
| `radbot/web/api/session/session_proxy.py` | Proxy: spawn, discover, health-check, A2A message |
| `radbot/worker/db.py` | `session_workers` table CRUD |

## CI/CD

- `.github/workflows/docker-build.yml` — builds on push to `main`, tags `v{MAJOR}.{BUILD}`
- Image: `ghcr.io/perrymanuk/radbot`
