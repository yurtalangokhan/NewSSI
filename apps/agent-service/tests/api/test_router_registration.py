"""Tests for centralized API route registration."""

from fastapi import FastAPI
from fastapi.routing import APIRoute

from core.http.api_versioning import API_PREFIX


def test_register_api_routes_populates_fastapi_app():
    """Verify that register_api_routes attaches all versioned routes to a FastAPI instance."""
    from api.router import ROUTERS, register_api_routes

    test_app = FastAPI()
    register_api_routes(test_app)

    routes = [r for r in test_app.routes if isinstance(r, APIRoute)]
    assert len(routes) > 0

    # Ensure all registered routes start with the API prefix
    for route in routes:
        assert route.path.startswith(f"{API_PREFIX}/"), (
            f"Route {route.path} does not start with {API_PREFIX}"
        )

    # Every router the routes package exports is registered: a count would break on
    # a deliberate removal yet miss a newly added router that was never mounted.
    import api.routes as routes_package

    exported = {
        name: getattr(routes_package, name)
        for name in routes_package.__all__
        if name.endswith("_router")
    }
    registered = {id(router) for router, _prefix in ROUTERS}
    assert exported
    assert [name for name, router in exported.items() if id(router) not in registered] == []


def test_production_app_routes_match_central_router():
    """Ensure the main production app routes match the centralized registration."""
    from app import app

    app_routes = [r for r in app.routes if isinstance(r, APIRoute)]
    assert len(app_routes) > 0

    # Every route in production app should have API_PREFIX
    for route in app_routes:
        assert route.path.startswith(f"{API_PREFIX}/"), (
            f"Route {route.path} in app does not start with {API_PREFIX}"
        )
