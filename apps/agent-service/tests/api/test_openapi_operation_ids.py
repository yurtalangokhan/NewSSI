"""operationId must be unique across the document.

The OpenAPI specification requires it, and code generators derive method names
from it: two operations sharing an id collide into one generated method, so one
of the endpoints silently becomes uncallable.

The service generates ids from the route's function name. That is readable, but
several route modules define the same function name — legacy and canonical paths
for the same resource, or a DELETE and a POST spelling of one action — so the
raw name is not unique on its own.
"""

import collections

from fastapi.routing import APIRoute

from app import app


def _operation_ids() -> list[str]:
    spec = app.openapi()
    return [
        operation["operationId"]
        for item in spec["paths"].values()
        for method, operation in item.items()
        if isinstance(operation, dict) and "operationId" in operation
    ]


def test_operation_ids_are_unique() -> None:
    duplicates = {
        name: count for name, count in collections.Counter(_operation_ids()).items() if count > 1
    }

    assert not duplicates, f"duplicate operationIds: {duplicates}"


def test_every_operation_has_an_operation_id() -> None:
    spec = app.openapi()
    operations = [
        (path, method)
        for path, item in spec["paths"].items()
        for method, operation in item.items()
        if isinstance(operation, dict) and method in {"get", "put", "post", "delete", "patch"}
    ]

    assert len(_operation_ids()) >= len(operations)


def test_non_colliding_routes_keep_their_plain_function_name() -> None:
    """Disambiguation must not churn ids that were already unique.

    Compared against the routes that actually reach the document: a route whose
    path and method duplicate an earlier one is shadowed by it and never appears,
    which is a separate defect from id collision.
    """
    # Mirror how the document is assembled: routes are merged into
    # paths[path][method], so when two routes share both, the later one wins and
    # the earlier is shadowed out of the spec entirely.
    reachable: dict[tuple, APIRoute] = {}
    for route in app.routes:
        if isinstance(route, APIRoute) and route.include_in_schema:
            for method in route.methods:
                reachable[(route.path_format, method)] = route

    names = collections.Counter(route.name for route in reachable.values())
    unique_names = {name for name, count in names.items() if count == 1}
    ids = set(_operation_ids())

    missing = sorted(unique_names - ids)
    assert not missing, f"these unique route names were renamed unnecessarily: {missing[:10]}"
