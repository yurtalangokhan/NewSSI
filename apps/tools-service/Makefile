.PHONY: install dev-install run test lint format fix typecheck validate clean

install:
	uv sync --frozen

dev-install:
	uv sync --frozen --all-groups

run:
	uv run python server.py

test:
	uv run pytest

lint:
	uv run ruff check --config ruff.toml src/

format:
	uv run ruff format --config ruff.toml src/

fix:
	uv run ruff check --config ruff.toml --fix src/

typecheck:
	uv run mypy src/

validate: lint typecheck test

clean:
	rm -rf .ruff_cache .mypy_cache .pytest_cache __pycache__ **/__pycache__ src/**/*.pyc
