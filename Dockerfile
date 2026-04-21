# syntax=docker/dockerfile:1

# Stage 1: Build React frontend
FROM node:20-slim AS frontend-build

WORKDIR /frontend
COPY radbot/web/frontend/package.json radbot/web/frontend/package-lock.json* radbot/web/frontend/.npmrc ./
RUN npm ci
COPY radbot/web/frontend/ .
RUN npx tsc -b && npx vite build --outDir dist

# Stage 2: Install Claude Code CLI (isolated from runtime)
FROM node:20-slim AS claude-code-build

RUN npm install -g @anthropic-ai/claude-code

# Seed Claude Code config to skip interactive onboarding wizard.
# The onboarding runs on first interactive launch regardless of auth;
# running once in -p mode creates the required state files.
RUN ANTHROPIC_API_KEY=sk-ant-dummy claude -p "hi" --max-turns 1 2>/dev/null || true \
    && mkdir -p /root/.claude \
    && echo '{"theme":"dark"}' > /root/.claude/settings.json \
    && echo '{}' > /root/.claude/settings.local.json

# Stage 3a: Fetch ast-grep prebuilt binary for code exploration tools (EX9).
# stack-graphs is archived/source-only; we use universal-ctags + ast-grep + rg
# instead. See radbot/tools/repo_exploration.py.
FROM debian:bookworm-slim AS ast-grep-bin
ARG AST_GREP_VERSION=0.42.1
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates unzip \
    && curl -fsSL -o /tmp/ast-grep.zip \
       "https://github.com/ast-grep/ast-grep/releases/download/${AST_GREP_VERSION}/app-x86_64-unknown-linux-gnu.zip" \
    && unzip -j /tmp/ast-grep.zip -d /out \
    && chmod +x /out/ast-grep /out/sg \
    && rm -rf /var/lib/apt/lists/*

# Stage 3b: Fetch gh CLI prebuilt binary (static linux_amd64 tarball).
# Used by Claude Code / axel workflows for PR operations. Auth happens at
# runtime via GH_TOKEN — see /usr/local/bin/gh-token helper below.
FROM debian:bookworm-slim AS gh-cli-bin
ARG GH_CLI_VERSION=2.90.0
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && curl -fsSL -o /tmp/gh.tar.gz \
       "https://github.com/cli/cli/releases/download/v${GH_CLI_VERSION}/gh_${GH_CLI_VERSION}_linux_amd64.tar.gz" \
    && tar -xzf /tmp/gh.tar.gz -C /tmp \
    && mv "/tmp/gh_${GH_CLI_VERSION}_linux_amd64/bin/gh" /usr/local/bin/gh \
    && chmod +x /usr/local/bin/gh \
    && rm -rf /var/lib/apt/lists/* /tmp/gh.tar.gz "/tmp/gh_${GH_CLI_VERSION}_linux_amd64"

# Stage 3: Install Python dependencies (build tools available here only)
FROM python:3.14-slim AS python-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc git \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

WORKDIR /app

# Install Python dependencies (layer caching: only reruns when pyproject.toml changes)
COPY pyproject.toml README.md ./
RUN mkdir -p radbot && touch radbot/__init__.py
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -e ".[web]"

# Stage 4: Runtime image (no build tools)
FROM python:3.14-slim

# Runtime-only system deps: libpq5 (psycopg2 runtime), git (workspace clones),
# curl + ca-certificates (health checks, API calls)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 git curl ca-certificates ripgrep universal-ctags \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Code exploration binaries (EX9 / PT33). Scout reads cloned public repos
# from /data/repos using these read-only tools.
COPY --from=ast-grep-bin /out/ast-grep /usr/local/bin/ast-grep
COPY --from=ast-grep-bin /out/sg /usr/local/bin/sg
RUN mkdir -p /data/repos

# GitHub CLI (PT79) — for PR operations from Claude Code / axel workflows.
COPY --from=gh-cli-bin /usr/local/bin/gh /usr/local/bin/gh

# Global git identity for container-originated commits (PT79).
RUN git config --global user.name "radbot" \
    && git config --global user.email "radbot@local"

# Copy Node.js binary + Claude Code CLI (no npm/nodesource needed at runtime)
COPY --from=claude-code-build /usr/local/bin/node /usr/local/bin/node
COPY --from=claude-code-build /usr/local/lib/node_modules /usr/local/lib/node_modules
# Upstream @anthropic-ai/claude-code ships its entry at `bin/claude.exe`
# (a Node script — the .exe name is cross-platform, not Windows-specific).
# Keep this in sync with the package's "bin" field in its package.json.
RUN ln -s ../lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe /usr/local/bin/claude

# Copy Claude Code onboarding state
COPY --from=claude-code-build /root/.claude /root/.claude

# Create workspaces directory for cloned repos
RUN mkdir -p /app/workspaces

WORKDIR /app

# Copy Python packages from builder (no gcc/libpq-dev carried over)
COPY --from=python-builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages

# Copy application code
COPY radbot/ radbot/
COPY agent.py .

# Copy built frontend assets into the static directory
COPY --from=frontend-build /frontend/dist radbot/web/static/dist/

# Helper script (PT79): mint a short-lived GitHub App installation token
# using the existing radbot.tools.github.github_app_client. Intended use:
#     GH_TOKEN=$(gh-token) gh pr list
COPY scripts/gh_token.py /usr/local/bin/gh-token
RUN chmod +x /usr/local/bin/gh-token

# Environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    GH_PROMPT_DISABLED=1

EXPOSE 8000

CMD ["python", "-m", "radbot.web", "--host", "0.0.0.0", "--port", "8000"]
