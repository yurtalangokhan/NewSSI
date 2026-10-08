"""The published error contract must be a valid, resolvable OpenAPI document.

Two failures are pinned here. First, every operation has to advertise the error
envelope it can actually return. Second — and less obvious — the envelope schema
placed in ``components/schemas`` must not carry Pydantic's ``$defs`` block: those
produce ``#/$defs/...`` pointers, which resolve against the *document root* and
find nothing, so Swagger UI and every code generator break on the spec.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from error_contract import (
    ERROR_RESPONSES,
    ErrorEnvelope,
    error_responses,
    register_error_handlers,
)


def _spec() -> dict:
    app = FastAPI(title="Test API", version="9.9.9", responses=ERROR_RESPONSES)
    register_error_handlers(app, service_name="test")

    @app.get("/things")
    async def things() -> dict[str, str]:
        return {"ok": "yes"}

    return TestClient(app).get("/openapi.json").json()


def _iter_refs(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                yield value
            else:
                yield from _iter_refs(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_refs(item)


def test_every_operation_declares_the_error_contract() -> None:
    operation = _spec()["paths"]["/things"]["get"]

    assert {
        "400",
        "401",
        "403",
        "404",
        "409",
        "413",
        "415",
        "422",
        "429",
        "500",
        "502",
        "503",
        "504",
    } <= set(operation["responses"])


def test_error_responses_reference_the_envelope_schema() -> None:
    operation = _spec()["paths"]["/things"]["get"]

    schema = operation["responses"]["500"]["content"]["application/json"]["schema"]
    assert schema == {"$ref": "#/components/schemas/ErrorEnvelope"}


def test_envelope_schema_is_published_in_components() -> None:
    assert "ErrorEnvelope" in _spec()["components"]["schemas"]


def test_document_contains_no_dangling_references() -> None:
    spec = _spec()

    for ref in _iter_refs(spec):
        assert ref.startswith("#/components/"), f"non-component reference: {ref}"
        node = spec
        for part in ref.removeprefix("#/").split("/"):
            assert part in node, f"unresolvable reference: {ref}"
            node = node[part]


def test_error_responses_can_be_narrowed_per_route() -> None:
    subset = error_responses(404, 409)

    assert set(subset) == {404, 409}
    assert subset[409]["model"] is ErrorEnvelope


def test_unknown_status_code_is_rejected() -> None:
    try:
        error_responses(418)
    except ValueError as exc:
        assert "418" in str(exc)
    else:
        raise AssertionError("expected a ValueError for an uncontracted status code")


def test_routing_errors_use_the_documented_envelope() -> None:
    """A 404 raised by the router must match what the spec advertises.

    Starlette's router raises ``starlette.exceptions.HTTPException``. FastAPI's
    ``HTTPException`` subclasses it, so a handler registered only for the FastAPI
    class never matches a routing error and FastAPI's ``{"detail": ...}`` default
    is returned instead — contradicting the published contract.
    """
    app = FastAPI(responses=ERROR_RESPONSES)
    register_error_handlers(app, service_name="test")

    response = TestClient(app).get("/no-such-route")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "request.not_found"


def test_method_not_allowed_uses_the_documented_envelope() -> None:
    app = FastAPI(responses=ERROR_RESPONSES)
    register_error_handlers(app, service_name="test")

    @app.get("/things")
    async def things() -> dict[str, str]:
        return {}

    response = TestClient(app).post("/things")

    assert response.status_code == 405
    assert "error" in response.json()


def test_colliding_operation_ids_are_disambiguated() -> None:
    """Two handlers sharing a function name must not share an operationId.

    The spec requires operationId to be unique, and generators derive method
    names from it: a collision silently makes one endpoint uncallable.
    """
    app = FastAPI(responses=ERROR_RESPONSES, generate_unique_id_function=lambda route: route.name)
    register_error_handlers(app, service_name="test")

    @app.get("/legacy/items/{item_id}", name="get_item")
    async def legacy_get_item(item_id: int) -> dict[str, int]:
        return {}

    @app.get("/items/{item_id}", name="get_item")
    async def get_item(item_id: int) -> dict[str, int]:
        return {}

    spec = TestClient(app).get("/openapi.json").json()
    ids = [
        op["operationId"]
        for item in spec["paths"].values()
        for op in item.values()
        if isinstance(op, dict) and "operationId" in op
    ]

    assert len(ids) == len(set(ids)), f"duplicate operationIds: {ids}"


def test_unique_operation_ids_are_left_alone() -> None:
    """Disambiguation must not churn ids that were already unique."""
    app = FastAPI(responses=ERROR_RESPONSES, generate_unique_id_function=lambda route: route.name)
    register_error_handlers(app, service_name="test")

    @app.get("/things")
    async def list_things() -> dict[str, str]:
        return {}

    spec = TestClient(app).get("/openapi.json").json()

    assert spec["paths"]["/things"]["get"]["operationId"] == "list_things"
