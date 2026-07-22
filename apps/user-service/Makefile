.PHONY: install dev-install run test test-coverage lint format fix typecheck validate clean db-up db-down db-migrate db-migrate-create db-migrate-rollback db-reset

install:
	uv sync --frozen

dev-install:
	uv sync --frozen --all-groups

run:
	uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8090

test:
	uv run pytest

test-coverage:
	uv run pytest --cov=src --cov-report=html --cov-report=term

lint:
	uv run ruff check src/

format:
	uv run ruff format src/

fix:
	uv run ruff check --fix src/

typecheck:
	uv run mypy src/

validate: lint typecheck test

clean:
	rm -rf .ruff_cache .mypy_cache .pytest_cache __pycache__ **/__pycache__ src/**/*.pyc

db-up:
	docker compose -f compose.yaml up -d user-service-db

db-down:
	docker compose -f compose.yaml down

db-migrate:
	uv run alembic upgrade head

db-migrate-create:
	@read -p "Migration name: " name; \
	uv run alembic revision --autogenerate -m "$$name"

db-migrate-rollback:
	uv run alembic downgrade -1

db-reset:
	uv run alembic downgrade base && uv run alembic upgrade head
