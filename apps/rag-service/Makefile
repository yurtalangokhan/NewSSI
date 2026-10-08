.PHONY: install dev-install run test lint format fix typecheck validate clean build up up-dev down logs restart

install:
	uv sync --frozen

dev-install:
	uv sync --frozen --all-groups

run:
	uv run python -m src.server

TEST_FILE ?= tests/unit_tests

test:
	IS_TESTING=true uv run pytest $(TEST_FILE)

lint:
	uv run ruff check --config ruff.toml .

format:
	uv run ruff format --config ruff.toml .
	uv run ruff check --config ruff.toml --fix .

fix:
	uv run ruff check --config ruff.toml --fix .

typecheck:
	uv run mypy src/

validate: lint typecheck test

clean:
	rm -rf .ruff_cache .mypy_cache .pytest_cache __pycache__ **/__pycache__ src/**/*.pyc

build:
	docker compose build

up:
	docker compose up -d

up-dev:
	docker compose up

down:
	docker compose down

logs:
	docker compose logs -f

restart:
	docker compose restart
