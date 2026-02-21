.PHONY: help setup setup-web setup-frontend test test-unit test-integration test-e2e test-e2e-core test-e2e-api test-e2e-agent test-e2e-integrations test-e2e-docker test-e2e-docker-up test-e2e-docker-down seed-docker lint format run-cli run-web run-web-custom run-scheduler dev-frontend build-frontend clean docker-build docker-up docker-down docker-logs docker-clean

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
	@echo "Docker e2e test targets:"
	@echo "  make test-e2e-docker      # Start stack, seed credentials, run e2e tests, tear down"
	@echo "  make test-e2e-docker-up   # Start docker stack for manual test runs"
	@echo "  make test-e2e-docker-down # Tear down docker stack"
	@echo "  make seed-docker          # Seed running docker stack with local dev credentials"

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

test-e2e:
	RADBOT_ENV=dev $(PYTEST) tests/e2e -v --timeout=120

test-e2e-core:
	RADBOT_ENV=dev $(PYTEST) tests/e2e/test_health.py tests/e2e/test_sessions_api.py tests/e2e/test_websocket_basic.py -v

test-e2e-api:
	RADBOT_ENV=dev $(PYTEST) tests/e2e/test_tasks_api.py tests/e2e/test_scheduler_api.py tests/e2e/test_reminders_api.py tests/e2e/test_webhooks_api.py tests/e2e/test_memory_api.py -v

test-e2e-agent:
	RADBOT_ENV=dev $(PYTEST) tests/e2e/test_agent_chat.py tests/e2e/test_agent_routing.py -v --timeout=180

test-e2e-integrations:
	RADBOT_ENV=dev $(PYTEST) tests/e2e/test_integration_ha.py tests/e2e/test_integration_calendar.py tests/e2e/test_integration_gmail.py tests/e2e/test_integration_jira.py tests/e2e/test_integration_overseerr.py tests/e2e/test_integration_picnic.py -v --timeout=180

test-e2e-docker:
	docker compose up -d --build --wait
	RADBOT_ENV=dev $(PYTHON) scripts/seed_docker_credentials.py \
		--target-url http://localhost:$${RADBOT_EXPOSED_PORT:-8001} \
		--admin-token $$(grep '^RADBOT_ADMIN_TOKEN=' .env | cut -d= -f2-) \
		--rewrite-localhost || true
	RADBOT_TEST_URL=http://localhost:$${RADBOT_EXPOSED_PORT:-8001} \
	RADBOT_ADMIN_TOKEN=$$(grep '^RADBOT_ADMIN_TOKEN=' .env | cut -d= -f2-) \
	$(PYTEST) tests/e2e -v --timeout=120 ; \
	EXIT_CODE=$$? ; \
	docker compose down ; \
	exit $$EXIT_CODE

test-e2e-docker-up:
	docker compose up -d --wait

test-e2e-docker-down:
	docker compose down

seed-docker:
	RADBOT_ENV=dev $(PYTHON) scripts/seed_docker_credentials.py \
		--target-url http://localhost:$${RADBOT_EXPOSED_PORT:-8001} \
		--admin-token $$(grep '^RADBOT_ADMIN_TOKEN=' .env | cut -d= -f2-) \
		--rewrite-localhost

lint:
	flake8 radbot tests
	mypy radbot tests
	black --check radbot tests
	isort --check radbot tests

format:
	black radbot tests
	isort radbot tests

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
