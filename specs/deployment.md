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

When `config:agent` → `session_mode = "remote"`, each chat session runs as a persistent Nomad service job (`type = "service"`). Workers hold full ADK session state in memory, expose A2A endpoints, and restart on crash. The main app proxies messages via `SessionProxy`.

See **`specs/workers.md`** for full architecture, protocol details, and file inventory.

## CI/CD

- `.github/workflows/docker-build.yml` — builds on push to `main`, tags `v{MAJOR}.{BUILD}`
- Image: `ghcr.io/perrymanuk/radbot`
