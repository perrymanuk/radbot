.PHONY: help setup setup-web setup-frontend test test-unit test-integration lint format run-cli run-web run-web-custom run-scheduler dev-frontend build-frontend clean docker-build docker-up docker-down docker-logs docker-clean

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
