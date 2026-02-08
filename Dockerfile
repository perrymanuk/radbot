FROM python:3.10-slim AS base

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install Python dependencies first (layer caching)
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[web]" || true

# Copy application code
COPY radbot/ radbot/
COPY agent.py .

# Re-run install so the editable package picks up the source
RUN pip install --no-cache-dir -e ".[web]"

# Environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

EXPOSE 8000

CMD ["python", "-m", "radbot.web", "--host", "0.0.0.0", "--port", "8000"]
