"""Helpers for tests that replace the authentication dependencies of a FastAPI app.

``FastAPI.include_router`` no longer copies the router's routes onto the
application: they live behind an included-router node, so walking
``app.routes`` for ``route.dependant`` finds nothing and leaves every
dependency un-overridden (requests then fail authentication with 401). These
helpers walk the included routers explicitly, so the tests do not depend on
how a particular FastAPI release stores included routes.
"""

from collections.abc import Callable, Iterator
from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute


def iter_api_routes(app: FastAPI) -> Iterator[APIRoute]:
    """Yield every concrete route of ``app``, including routes of included routers."""
    pending: list[Any] = list(app.router.routes)
    while pending:
        route = pending.pop()
        if isinstance(route, APIRoute):
            yield route
            continue
        included = getattr(route, "original_router", None)
        if included is not None:
            pending.extend(included.routes)


def iter_route_paths(app: FastAPI) -> Iterator[str]:
    """Yield the full public path of every route, including each included router's prefix."""
    pending: list[tuple[Any, str]] = [(route, "") for route in app.router.routes]
    while pending:
        route, prefix = pending.pop()
        included = getattr(route, "original_router", None)
        if included is not None:
            context = getattr(route, "include_context", None)
            nested = prefix + (getattr(context, "prefix", "") or "")
            pending.extend((child, nested) for child in included.routes)
        else:
            path = getattr(route, "path", None)
            if path is not None:
                yield prefix + path


def override_route_dependencies(app: FastAPI, factory: Callable[[], Any]) -> None:
    """Replace each route's direct dependencies (the auth/permission gates) with ``factory``."""
    for route in iter_api_routes(app):
        for dependency in route.dependant.dependencies:
            app.dependency_overrides[dependency.call] = factory
