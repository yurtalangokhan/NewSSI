# ruff: noqa: S101 -- Assertions express pytest expectations.
"""Every router failure goes through the shared response_errors contract."""

import ast
from pathlib import Path

import pytest

ROUTERS = sorted(Path(__file__).parents[2].joinpath("src").glob("*/router.py"))


def _called_names(node: ast.AST) -> set[str]:
    return {n.func.id for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}


@pytest.mark.parametrize("path", ROUTERS, ids=lambda path: f"{path.parent.name}/{path.name}")
def test_router_failures_use_response_errors(path):
    tree = ast.parse(path.read_text())
    helpers = {
        fn.name
        for fn in ast.walk(tree)
        if isinstance(fn, ast.FunctionDef) and {"set_error_response", "request_locale"} <= _called_names(fn)
    }
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ExceptHandler) and isinstance(node.type, ast.Name)):
            continue
        if node.type.id != "ApplicationError":
            continue
        called = set().union(*(_called_names(stmt) for stmt in node.body))
        assert called & helpers or {"set_error_response", "request_locale"} <= called, (
            f"{path.parent.name}/{path.name}:{node.lineno} bypasses response_errors"
        )
