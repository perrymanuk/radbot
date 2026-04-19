.PHONY: help setup setup-web setup-frontend test test-unit test-integration test-e2e test-e2e-up test-e2e-down test-e2e-browser test-e2e-browser-affected test-e2e-browser-dev _test-e2e-prepare seed-docker lint format run-cli run-web run-web-custom run-scheduler dev-frontend build-frontend clean docker-build docker-up docker-down docker-logs docker-clean

# Use uv for Python package management
PYTHON := uv run python
PIP := uv pip
PYTEST := uv run pytest
UV := uv
ADK := uv run adk

# Help target that lists all available targets with descriptions
help:
	@echo "radbot Makefile Targets:"
	@echo "=========================="
	@echo "setup          : Install development dependencies using uv"
	@echo "setup-web      : Install web-specific dependencies (Tavily, LangChain, FastAPI)"
	@echo "test           : Run all tests"
	@echo "test-unit      : Run only unit tests"
	@echo "test-integration: Run only integration tests"
	@echo "lint           : Run all linting checks (flake8, mypy, black, isort)"
	@echo "format         : Auto-format code with black and isort"
	@echo "run-cli        : Start the radbot CLI interface"
	@echo "run-web        : Start the radbot web interface using ADK"
	@echo "run-web-custom : Start the custom FastAPI web interface"
	@echo "run-scheduler  : Run the scheduler with optional arguments (use ARGS=\"--your-args\")"
	@echo "setup-frontend : Install React frontend npm dependencies"
	@echo "dev-frontend   : Start the Vite dev server (proxies API to FastAPI)"
	@echo "build-frontend : Build the React frontend for production"
	@echo "clean          : Remove build artifacts and cache files"
	@echo ""
	@echo "Example usage:"
	@echo "  make setup              # Install development dependencies"
	@echo "  make test               # Run all tests"
	@echo "  make run-cli            # Start the interactive CLI"
	@echo "  make run-web            # Start the web interface using ADK"
	@echo "  make run-web-custom     # Start the custom FastAPI web interface"
	@echo "  make run-scheduler ARGS=\"--additional-args\""
	@echo ""
	@echo "Docker targets:"
	@echo "  make docker-build   # Build the radbot Docker image"
	@echo "  make docker-up      # Start all services (postgres, qdrant, radbot)"
	@echo "  make docker-down    # Stop all services"
	@echo "  make docker-logs    # Tail radbot container logs"
	@echo "  make docker-clean   # Stop all services and remove volumes"
	@echo ""
	@echo "e2e test targets (Docker-based):"
	@echo "  make test-e2e                     # API e2e: pytest tests/e2e against Docker stack"
	@echo "  make test-e2e-browser             # Browser e2e: Playwright against Docker stack at :8001"
	@echo "  make test-e2e-browser-affected    # Same, but only specs whose covered files changed"
	@echo "  make test-e2e-browser-dev         # Browser e2e against Vite dev server (no Docker)"
	@echo "  make test-e2e-up                  # Start docker stack for manual test runs"
	@echo "  make test-e2e-down                # Tear down docker stack"
	@echo "  make seed-docker                  # Seed running docker stack with local dev credentials"

# Set help as the default target
.DEFAULT_GOAL := help

setup:
	$(UV) pip install -e ".[dev]"
	$(UV) pip install --upgrade pip

setup-web:
	$(UV) pip install -e ".[web]"
	@echo "Web dependencies installed successfully"

test:
	$(PYTEST)

test-unit:
	$(PYTEST) tests/unit

test-integration:
	$(PYTEST) tests/integration

# Internal helper: bring stack up, seed dev credentials, restart, wait healthy.
# Used by test-e2e and test-e2e-browser to share the bootstrap step.
_test-e2e-prepare:
	docker compose up -d --build --wait
	RADBOT_ENV=dev $(PYTHON) scripts/seed_docker_credentials.py \
		--target-url http://localhost:$${RADBOT_EXPOSED_PORT:-8001} \
		--admin-token $$(grep '^RADBOT_ADMIN_TOKEN=' .env | cut -d= -f2-) \
		--rewrite-localhost || true
	@echo "Restarting radbot to pick up seeded credentials..."
	docker compose restart radbot
	$(PYTHON) scripts/wait_for_health.py \
		--url http://localhost:$${RADBOT_EXPOSED_PORT:-8001}/health \
		--timeout 60 --interval 2

test-e2e: _test-e2e-prepare
	RADBOT_TEST_URL=http://localhost:$${RADBOT_EXPOSED_PORT:-8001} \
	RADBOT_ADMIN_TOKEN=$$(grep '^RADBOT_ADMIN_TOKEN=' .env | cut -d= -f2-) \
	$(PYTEST) tests/e2e -v --timeout=120 ; \
	EXIT_CODE=$$? ; \
	docker compose down ; \
	exit $$EXIT_CODE

# Browser e2e (Playwright) — runs against the same Docker stack as test-e2e.
# Requires `npx playwright install chromium` once after `npm install`.
test-e2e-browser: _test-e2e-prepare
	cd radbot/web/frontend && npm run build
	cd radbot/web/frontend && PLAYWRIGHT_BASE_URL=http://localhost:$${RADBOT_EXPOSED_PORT:-8001} \
		RADBOT_ADMIN_TOKEN=$$(cd ../../../ && grep '^RADBOT_ADMIN_TOKEN=' .env | cut -d= -f2-) \
		npm run test:e2e ; \
	EXIT_CODE=$$? ; \
	cd ../../.. && docker compose down ; \
	exit $$EXIT_CODE

# Browser e2e — only the specs whose covered files changed vs origin/main.
test-e2e-browser-affected: _test-e2e-prepare
	cd radbot/web/frontend && npm run build
	cd radbot/web/frontend && PLAYWRIGHT_BASE_URL=http://localhost:$${RADBOT_EXPOSED_PORT:-8001} \
		RADBOT_ADMIN_TOKEN=$$(cd ../../../ && grep '^RADBOT_ADMIN_TOKEN=' .env | cut -d= -f2-) \
		BASE_REF=$${BASE_REF:-origin/main} \
		npm run test:e2e:affected ; \
	EXIT_CODE=$$? ; \
	cd ../../.. && docker compose down ; \
	exit $$EXIT_CODE

# Fast dev-loop: requires `make dev-frontend` (Vite :5173) + `make run-web-custom`
# (FastAPI :8000) already running. Skips Docker build entirely.
test-e2e-browser-dev:
	cd radbot/web/frontend && PLAYWRIGHT_BASE_URL=$${PLAYWRIGHT_BASE_URL:-http://localhost:5173} \
		npm run test:e2e

test-e2e-up:
	docker compose up -d --wait

test-e2e-down:
	docker compose down

seed-docker:
	RADBOT_ENV=dev $(PYTHON) scripts/seed_docker_credentials.py \
		--target-url http://localhost:$${RADBOT_EXPOSED_PORT:-8001} \
		--admin-token $$(grep '^RADBOT_ADMIN_TOKEN=' .env | cut -d= -f2-) \
		--rewrite-localhost

lint:
	$(UV) run flake8 radbot tests
	$(UV) run mypy radbot tests
	# black + isort intentionally not gated yet — running them would reformat
	# ~107 files at once (line-length 88 vs the codebase's actual style).
	# Tracked under Telos PT16 for incremental adoption.
	@echo "(skipping black/isort — tracked in Telos PT16)"

format:
	$(UV) run black radbot tests
	$(UV) run isort radbot tests

run-cli:
	$(PYTHON) -m radbot.cli.main

run-web: setup setup-web
	$(ADK) web
	
run-web-custom: setup setup-web
	$(PYTHON) -m radbot.web --reload

run-scheduler:
	$(PYTHON) -m radbot.cli.scheduler $(ARGS)

setup-frontend:
	cd radbot/web/frontend && npm install

dev-frontend:
	cd radbot/web/frontend && npm run dev

build-frontend:
	cd radbot/web/frontend && npm run build

docker-build:
	docker compose build

docker-up:
	docker compose up 

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f radbot

docker-clean:
	docker compose down -v

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	find . -type d -name "*.pytest_cache" -exec rm -rf {} +
	find . -type d -name "*.mypy_cache" -exec rm -rf {} +
