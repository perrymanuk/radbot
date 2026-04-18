# Deployment

## Production

- **Endpoint**: `https://radbot.demonsafe.com`
- **Nomad job**: `~/git/perrymanuk/hashi-homelab/nomad_jobs/ai-ml/radbot/nomad.job`
- **Docker image (main)**: `ghcr.io/perrymanuk/radbot` — auto-built by `.github/workflows/docker-build.yml` on push to `main`
- **Docker image (worker)**: `ghcr.io/perrymanuk/radbot-worker` — separate image, separate Dockerfile (`Dockerfile.worker`), separate build pipeline
- **Versioning**: Auto-incremented `v{MAJOR}.{BUILD}` tags (e.g. `v0.14`). Update the `image` tag in the Nomad job after pushing.
- **Reverse proxy**: Traefik via Consul service discovery. `ProxyHeadersMiddleware` handles `X-Forwarded-Proto`.

## Runtime Environment

- **Python**: 3.14-slim base image for both main app and worker (upgraded in `85a258e`)
- **Package manager**: `uv` — both containers use multi-stage builds with `uv` + GHA layer caching (`c20e8b2`, `c1cbdd8`)
- **ADK**: `google-adk>=1.31.0,<2.0.0` — the currently supported line after upstream unwound the v2 alpha (see CLAUDE.md gotchas)
- **genai**: `google-genai>=1.72.0` (ADK 1.31.0 floor; NOT the older `google-generativeai` package)

## Bootstrap Config

Nomad templates a minimal `config.yaml` with only `database:` section. All other config loaded from the DB credential store at startup.

| Env var | Purpose |
|---------|---------|
| `RADBOT_CREDENTIAL_KEY` | Fernet key for encrypted credentials in DB |
| `RADBOT_ADMIN_TOKEN` | Bearer token for `/admin/` API |
| `RADBOT_CONFIG_FILE` | Path to `config.yaml` (alias: `RADBOT_CONFIG`; Nomad uses the `_FILE` variant) |
| `RADBOT_ENV` | `dev` loads `config.dev.yaml` instead of `config.yaml` |
| `RADBOT_WORKER_IMAGE_TAG` | Overrides `config:agent.worker_image_tag` for newly-spawned workspace workers |

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

### Reverse Proxy Gotchas

- FastAPI behind Traefik generates redirect URLs using the internal HTTP scheme. `ProxyHeadersMiddleware` in `web/app.py` trusts `X-Forwarded-Proto`.
- FastAPI router root paths (`@router.get("/")`) 307-redirect without trailing slash. On HTTPS this can produce `http://` redirects that browsers block as mixed content. **Always use trailing slashes** in frontend fetch calls that hit router root paths.

## Workspace/Terminal Workers (Remote Mode)

When `config:agent.session_mode = "remote"`, each terminal workspace runs as a persistent Nomad **service** job:

- `type = "service"` with `restart: attempts=1, mode=fail`
- Image: `ghcr.io/perrymanuk/radbot-worker:{tag}` (separate from main app)
- Each worker registers with Nomad service discovery (`radbot-workspace`) tagged `workspace_id=<UUID>`
- Bootstrap env templated from the main app's DB credential store (`RADBOT_CREDENTIAL_KEY`, `RADBOT_ADMIN_TOKEN`, `postgres_pass`)
- Pre-spawned on workspace *creation* for instant cold-start on first click (`3e93b63`)

Chat sessions always run in-process — `session_mode` no longer affects chat (`12e4901`).

See **`specs/workers.md`** for full architecture, worker protocol, and file inventory.

## CI/CD

- `.github/workflows/docker-build.yml` — builds main image on push to `main`, tags `v{MAJOR}.{BUILD}`, pushes to GHCR
- Separate worker image pipeline with BuildKit + GHA layer caching
- Image: `ghcr.io/perrymanuk/radbot` (main), `ghcr.io/perrymanuk/radbot-worker` (worker)
- Update the Nomad job's `image` tag after a new version pushes (manual step)

## Environment Separation (Dev)

Setting `RADBOT_ENV=dev`:

- Loads `config.dev.yaml` before `config.yaml` in each search directory
- Recommended separate prod/dev: PostgreSQL DB (`radbot_dev`), Qdrant collection (`radbot_dev`)
- Startup banner in `app.py` logs env, config path, database, qdrant collection — check at startup to verify

See `docs/implementation/dev_environment_setup.md` for full procedure.
