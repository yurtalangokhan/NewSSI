"""No route may be made unreachable by an earlier registration.

Starlette matches in registration order and takes the first full match, so a
parameterised path registered before a literal one swallows it: with
``PUT /providers/{provider_id}`` registered first, ``PUT /providers/order``
never runs — the request lands in ``update_provider`` with
``provider_id="order"`` instead.

Note this is the opposite of how the OpenAPI document is assembled, where paths
are merged into a dict and the *last* registration wins. That is why a shadowed
route can be documented as though it were live.
"""

import re

import pytest
from fastapi.routing import APIRoute
from starlette.routing import Match

from app import app


def _resolve(method: str, path: str) -> str | None:
    """Return the name of the route Starlette would actually run."""
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [],
        "root_path": "",
        "query_string": b"",
    }
    for route in app.routes:
        match, _ = route.matches(scope)
        if match == Match.FULL:
            return getattr(route, "name", None)
    return None


@pytest.mark.parametrize(
    ("method", "path", "expected"),
    [
        ("PUT", "/api/v1/admin/providers/order", "reorder_providers"),
        ("GET", "/api/v1/llm/persona/3/providers", "get_persona_providers"),
    ],
)
def test_literal_routes_are_reachable(method: str, path: str, expected: str) -> None:
    assert _resolve(method, path) == expected


def _shadowed_routes() -> list[tuple[str, str, str]]:
    """Routes an earlier registration already fully matches."""
    routes = [r for r in app.routes if isinstance(r, APIRoute) and r.include_in_schema]
    shadowed = []
    for index, route in enumerate(routes):
        url = re.sub(r"\{[^}]+\}", "1", route.path_format)
        for earlier in routes[:index]:
            if not earlier.methods & route.methods:
                continue
            pattern = "^" + re.sub(r"\{[^}]+\}", "[^/]+", earlier.path_format) + "$"
            if re.match(pattern, url):
                shadowed.append((min(route.methods & earlier.methods), url, route.name))
                break
    return shadowed


def test_no_route_is_unreachable() -> None:
    """Every registered route must be reachable.

    An unreachable route is worse than a missing one: it is documented, it looks
    maintained, and editing it has no effect — which is exactly how a fix to the
    MCP admin endpoints sat inert for weeks.
    """
    shadowed = _shadowed_routes()

    assert shadowed == [], (
        f"unreachable routes: {shadowed}. See docs/architecture/shadowed-routes.md"
    )


def test_the_surviving_admin_mcp_route_still_serves() -> None:
    """admin_mcp_route keeps the one endpoint that was never shadowed."""
    assert _resolve("GET", "/api/v1/admin/mcp/server/abc-123") == "get_mcp_server"
