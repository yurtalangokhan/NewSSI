# ruff: noqa: S101 -- Assertions express pytest expectations.
"""Every route failure goes through the shared response_errors contract."""

import ast
from pathlib import Path

import pytest

ROUTES = sorted(Path(__file__).parents[1].joinpath("src/api/routes").glob("*_route.py"))


def _application_error_handlers(path: Path) -> list[ast.ExceptHandler]:
    return [
        node
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.ExceptHandler) and isinstance(node.type, ast.Name) and node.type.id == "ApplicationError"
    ]


def _called_names(handler: ast.ExceptHandler) -> set[str]:
    return {
        node.func.id for stmt in handler.body for node in ast.walk(stmt) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


@pytest.mark.parametrize("path", ROUTES, ids=lambda path: path.name)
def test_route_failures_use_response_errors(path):
    for handler in _application_error_handlers(path):
        called = _called_names(handler)
        assert "set_error_response" in called, f"{path.name}:{handler.lineno} bypasses set_error_response"
        assert "request_locale" in called, f"{path.name}:{handler.lineno} renders a non-localized message"
