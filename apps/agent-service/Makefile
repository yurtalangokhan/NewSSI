# Makefile for agent-service
# Usage: make <target>

# Configuration
PROJECT_DIR := .
PYTHON := python
PYTEST := pytest
VENV_ACTIVATE := .venv/bin/activate
ALEMBIC := alembic
PRE_COMMIT := pre-commit

# Colors
GREEN := $(shell tput setaf 2 2>/dev/null)
YELLOW := $(shell tput setaf 3 2>/dev/null)
RESET := $(shell tput sgr0 2>/dev/null)

.PHONY: help install install-dev install-client sync sync-all clean test test-cov test-all test-file lint format fix typecheck validate run run-service run-streamlit run-studio docker-up docker-build docker-down migrate new-migration precommit-install precommit-run check-env info

# Default target
help:
	@echo "$(GREEN)agent-service Management$(RESET)"
	@echo ""
	@echo "Usage: make <target>"
	@echo ""
	@echo "$(YELLOW)Installation$(RESET)"
	@echo "  install        Install production dependencies"
	@echo "  install-dev    Install all dependencies including dev"
	@echo "  install-client Install only client dependencies"
	@echo "  sync           Sync dependencies (alias for install)"
	@echo "  sync-all       Sync all groups including dev"
	@echo ""
	@echo "$(YELLOW)Running$(RESET)"
	@echo "  run-service    Run FastAPI service"
	@echo "  run-streamlit  Run Streamlit app"
	@echo "  run-studio     Run LangGraph Studio"
	@echo ""
	@echo "$(YELLOW)Testing$(RESET)"
	@echo "  test           Run core tests (no streamlit required)"
	@echo "  test-cov       Run tests with coverage (terminal + HTML)"
	@echo "  test-all       Run all tests (requires client group)"
	@echo "  test-file      Run tests for specific file (FILE=path)"
	@echo ""
	@echo "$(YELLOW)Code Quality$(RESET)"
	@echo "  lint           Run ruff linter"
	@echo "  format         Format code with ruff"
	@echo "  fix            Fix auto-fixable linting issues"
	@echo "  typecheck      Run mypy type checker"
	@echo "  validate       Run lint, typecheck, and tests"
	@echo ""
	@echo "$(YELLOW)Database$(RESET)"
	@echo "  migrate        Apply all database migrations"
	@echo "  new-migration Create new migration (NAME=\"description\")"
	@echo "  migration-status Show migration status"
	@echo ""
	@echo "$(YELLOW)Docker$(RESET)"
	@echo "  docker-up      Start services with docker compose (watch mode)"
	@echo "  docker-build   Build Docker images"
	@echo "  docker-down    Stop Docker services"
	@echo "  docker-logs    View Docker logs"
	@echo ""
	@echo "$(YELLOW)Pre-commit$(RESET)"
	@echo "  precommit-install  Install pre-commit hooks"
	@echo "  precommit-run      Run pre-commit hooks"
	@echo ""
	@echo "$(YELLOW)Utilities$(RESET)"
	@echo "  check-env      Check environment setup"
	@echo "  info           Show project info"
	@echo "  clean          Clean cache files"

# ============================================================
# Installation
# ============================================================

install sync:
	@echo "$(GREEN)Installing dependencies...$(RESET)"
	cd $(PROJECT_DIR) && uv sync --frozen

sync-all:
	@echo "$(GREEN)Installing all dependencies including dev...$(RESET)"
	cd $(PROJECT_DIR) && uv sync --frozen --all-groups

install-dev:
	$(MAKE) sync-all

install-client:
	@echo "$(GREEN)Installing client dependencies only...$(RESET)"
	cd $(PROJECT_DIR) && uv sync --frozen --only-group client

# ============================================================
# Running
# ============================================================

run-service:
	@echo "$(GREEN)Starting FastAPI service...$(RESET)"
	@echo "$(YELLOW)API available at: http://localhost:8080$(RESET)"
	@echo "$(YELLOW)API docs at: http://localhost:8080/redoc$(RESET)"
	@echo "$(YELLOW)NOTE: Using FAKE_MODEL for development$(RESET)"
	cd $(PROJECT_DIR) && PYTHONPATH=$(PROJECT_DIR)/src $(PYTHON) src/run_service.py

run-streamlit:
	@echo "$(GREEN)Starting Streamlit app...$(RESET)"
	@echo "$(YELLOW)App available at: http://localhost:8501$(RESET)"
	cd $(PROJECT_DIR) && streamlit run src/streamlit_app.py

run-studio:
	@echo "$(GREEN)Starting LangGraph Studio...$(RESET)"
	cd $(PROJECT_DIR) && langgraph dev

run: run-service

# ============================================================
# Testing
# ============================================================

test:
	@echo "$(GREEN)Running tests...$(RESET)"
	cd $(PROJECT_DIR) && uv run pytest --ignore=tests/app --ignore=tests/voice --ignore=tests/integration

test-cov:
	@echo "$(GREEN)Running tests with coverage...$(RESET)"
	cd $(PROJECT_DIR) && uv run pytest --ignore=tests/app --ignore=tests/voice --ignore=tests/integration --cov=src --cov-report=term-missing --cov-report=html

test-all:
	@echo "$(GREEN)Running all tests (requires client group)...$(RESET)"
	cd $(PROJECT_DIR) && uv sync --frozen --all-groups && uv run pytest --cov=src --cov-report=term-missing --cov-report=html

test-file:
ifndef FILE
	$(error FILE is required. Usage: make test-file FILE=tests/service/test_service.py)
endif
	@echo "$(GREEN)Running tests for $(FILE)...$(RESET)"
	cd $(PROJECT_DIR) && uv run pytest $(FILE)

# ============================================================
# Code Quality
# ============================================================

lint:
	@echo "$(GREEN)Running ruff linter...$(RESET)"
	cd $(PROJECT_DIR) && uv run ruff check --config ruff.toml src/ tests/

format:
	@echo "$(GREEN)Formatting code with ruff...$(RESET)"
	cd $(PROJECT_DIR) && uv run ruff format --config ruff.toml src/ tests/

fix:
	@echo "$(GREEN)Fixing auto-fixable linting issues...$(RESET)"
	cd $(PROJECT_DIR) && uv run ruff check --config ruff.toml --fix src/ tests/

typecheck:
	@echo "$(GREEN)Running mypy type checker...$(RESET)"
	cd $(PROJECT_DIR) && uv run mypy src/

validate: lint typecheck test

# ============================================================
# Database Migrations
# ============================================================

migrate:
	@echo "$(GREEN)Applying database migrations...$(RESET)"
	cd $(PROJECT_DIR) && $(ALEMBIC) upgrade head

new-migration:
ifndef NAME
	$(error NAME is required. Usage: make new-migration NAME=\"add_new_table\")
endif
	@echo "$(GREEN)Creating migration: $(NAME)$(RESET)"
	cd $(PROJECT_DIR) && $(ALEMBIC) revision --autogenerate -m "$(NAME)"

migration-status:
	@echo "$(GREEN)Checking migration status...$(RESET)"
	cd $(PROJECT_DIR) && $(ALEMBIC) current

# ============================================================
# Docker
# ============================================================

docker-up:
	@echo "$(GREEN)Starting Docker services in watch mode...$(RESET)"
	@echo "$(YELLOW)Press Ctrl+C to stop$(RESET)"
	cd $(PROJECT_DIR) && docker compose watch

docker-build:
	@echo "$(GREEN)Building Docker images...$(RESET)"
	cd $(PROJECT_DIR) && docker compose build

docker-down:
	@echo "$(GREEN)Stopping Docker services...$(RESET)"
	cd $(PROJECT_DIR) && docker compose down

docker-logs:
	cd $(PROJECT_DIR) && docker compose logs -f

# ============================================================
# Pre-commit
# ============================================================

precommit-install:
	@echo "$(GREEN)Installing pre-commit hooks...$(RESET)"
	cd $(PROJECT_DIR) && $(PRE_COMMIT) install

precommit-run:
	@echo "$(GREEN)Running pre-commit hooks...$(RESET)"
	cd $(PROJECT_DIR) && $(PRE_COMMIT) run --all-files

# ============================================================
# Utilities
# ============================================================

check-env:
	@echo "$(GREEN)Checking environment setup...$(RESET)"
	@if [ -f "$(PROJECT_DIR)/.env" ]; then \
		echo "✓ .env file exists"; \
	else \
		echo "✗ .env file missing - create from .env.example"; \
	fi
	@if [ -d "$(PROJECT_DIR)/.venv" ]; then \
		echo "✓ Virtual environment exists"; \
	else \
		echo "✗ Virtual environment missing - run 'make install'"; \
	fi
	@echo "$(GREEN)Checking Python packages...$(RESET)"
	@cd $(PROJECT_DIR) && uv sync --frozen --check

info:
	@echo "$(GREEN)Project Information$(RESET)"
	@echo "Project: agent-service-toolkit"
	@echo "Python version: $$(${PYTHON} --version)"
	@echo "UV version: $$(${PROJECT_DIR}/.venv/bin/uv --version 2>/dev/null || echo 'not installed')"
	@echo ""
	@echo "$(YELLOW)Available agents:$(RESET)"
	@cd $(PROJECT_DIR) && ls -1 src/agents/*.py 2>/dev/null | xargs -n1 basename | sed 's/.py$$//' || echo "  (none found)"

clean:
	@echo "$(GREEN)Cleaning cache files...$(RESET)"
	find $(PROJECT_DIR) -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find $(PROJECT_DIR) -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find $(PROJECT_DIR) -type f -name "*.pyc" -delete 2>/dev/null || true
	find $(PROJECT_DIR) -type f -name "*.pyo" -delete 2>/dev/null || true
	find $(PROJECT_DIR) -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find $(PROJECT_DIR) -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo "✓ Cache files cleaned"
