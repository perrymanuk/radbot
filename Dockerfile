# Stage 1: Build React frontend
FROM node:20-slim AS frontend-build

WORKDIR /frontend
COPY radbot/web/frontend/package.json radbot/web/frontend/package-lock.json* ./
RUN npm ci
COPY radbot/web/frontend/ .
RUN npx tsc -b && npx vite build --outDir dist

# Stage 2: Python application
FROM python:3.12-slim AS base

# Install system dependencies, Node.js 20 (for Claude Code CLI), and git
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc git curl ca-certificates gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
       | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
       > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Create workspaces directory for cloned repos
RUN mkdir -p /app/workspaces

WORKDIR /app

# Copy and install Python dependencies first (layer caching)
COPY pyproject.toml README.md ./
# Create a minimal package dir so hatchling can resolve metadata for dep install
RUN mkdir -p radbot && touch radbot/__init__.py \
    && pip install --no-cache-dir -e ".[web]"

# Copy application code (overwrites the stub radbot/ from above)
COPY radbot/ radbot/
COPY agent.py .

# Copy built frontend assets into the static directory
COPY --from=frontend-build /frontend/dist radbot/web/static/dist/

# Re-run install so the editable package picks up all source files
RUN pip install --no-cache-dir -e ".[web]"

# Environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

EXPOSE 8000

CMD ["python", "-m", "radbot.web", "--host", "0.0.0.0", "--port", "8000"]
