"""Guard tests: one handler function exposes exactly one endpoint.

Route aliases used to be declared as extra decorators on the same handler
(``@router.post("/{agent_id}/invoke")`` plus ``@router.post("/invoke")``) or as
a second method on the same path (``PUT`` plus ``PATCH``). Each alias pair
doubled the surface of a single behavior: two contracts to document, two
idempotency entries to keep in sync, and one of them inevitably drifted.

Every pair has been collapsed to a single canonical route. These tests fail if
the pattern is reintroduced.
"""

import ast
from collections import defaultdict
from pathlib import Path

from fastapi.routing import APIRoute

from app import app
from core.http.api_versioning import API_PREFIX

ROUTE_METHODS = {"get", "post", "put", "patch", "delete"}
ROUTE_MODULE_DIR = Path(__file__).resolve().parents[2] / "src" / "api" / "routes"


def _route_modules() -> list[Path]:
    return sorted(ROUTE_MODULE_DIR.glob("*.py"))


def _handlers_with_route_decorators():
    for module_path in _route_modules():
        tree = ast.parse(module_path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            decorators = [
                decorator
                for decorator in node.decorator_list
                if isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr in ROUTE_METHODS
            ]
            if decorators:
                yield module_path.name, node, decorators


def _api_routes() -> list[APIRoute]:
    return [route for route in app.routes if isinstance(route, APIRoute)]


def test_no_handler_declares_more_than_one_route() -> None:
    offenders = [
        f"{module}:{node.lineno}:{node.name} declares {len(decorators)} route decorators"
        for module, node, decorators in _handlers_with_route_decorators()
        if len(decorators) > 1
    ]

    assert offenders == []


def test_no_route_is_registered_for_the_same_method_twice() -> None:
    registrations: dict[tuple[str, str], list[str]] = defaultdict(list)
    for route in _api_routes():
        for method in route.methods or set():
            registrations[(method, route.path)].append(route.name)

    duplicates = {
        f"{method} {path}": names
        for (method, path), names in registrations.items()
        if len(names) > 1
    }

    assert duplicates == {}


def test_every_registered_route_uses_the_versioned_prefix() -> None:
    offenders = sorted(
        {route.path for route in _api_routes() if not route.path.startswith(f"{API_PREFIX}/")}
    )

    assert offenders == []
