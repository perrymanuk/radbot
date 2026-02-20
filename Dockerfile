# Stage 1: Build React frontend
FROM node:20-slim AS frontend-build

WORKDIR /frontend
COPY radbot/web/frontend/package.json radbot/web/frontend/package-lock.json* ./
RUN npm ci
COPY radbot/web/frontend/ .
RUN npx tsc -b && npx vite build --outDir dist

# Stage 2: Python application
FROM python:3.12-slim AS base

# Install system dependencies (no Node needed at runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install Python dependencies first (layer caching)
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir -e ".[web]" || true

# Copy application code
COPY radbot/ radbot/
COPY agent.py .

# Copy built frontend assets into the static directory
COPY --from=frontend-build /frontend/dist radbot/web/static/dist/

# Re-run install so the editable package picks up the source
RUN pip install --no-cache-dir -e ".[web]"

# Environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

EXPOSE 8000

CMD ["python", "-m", "radbot.web", "--host", "0.0.0.0", "--port", "8000"]
