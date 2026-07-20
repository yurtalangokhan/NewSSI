.PHONY: install dev-install run test lint format fix typecheck clean

install:
	uv sync --frozen

dev-install:
	uv sync --frozen --all-groups

run:
	uv run python server.py

test:
	uv run pytest

lint:
	uv run ruff check src/

format:
	uv run ruff format src/

fix:
	uv run ruff check --fix src/

typecheck:
	uv run mypy src/

clean:
	rm -rf .ruff_cache .mypy_cache .pytest_cache __pycache__ **/__pycache__ src/**/*.pyc
