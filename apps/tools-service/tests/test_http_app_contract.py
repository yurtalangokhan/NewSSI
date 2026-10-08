"""tools-service must expose the same HTTP contract as the other three services.

Previously ``build_http_app()`` returned the raw FastMCP Starlette app and the
OpenAPI document was a hand-maintained dict: it described three paths, drifted
from the code by construction, declared no error schemas, and left ``/health``
with no failure response at all. The service is now a FastAPI application with
the MCP transport mounted inside it, so the document is generated from the
routes that actually exist.
"""

import pytest
from fastapi import FastAPI


@pytest.fixture(scope="module")
def app(http_app) -> FastAPI:
    return http_app


@pytest.fixture(scope="module")
def client(http_client):
    return http_client


@pytest.fixture(scope="module")
def spec(app: FastAPI) -> dict:
    return app.openapi()


def test_build_http_app_returns_a_fastapi_application(app: FastAPI) -> None:
    assert isinstance(app, FastAPI)


def test_openapi_is_generated_not_hand_written(spec: dict) -> None:
    assert spec["info"]["title"] == "Tools Service API"
    assert spec["info"]["version"] == "1.0.0"
    assert spec["info"]["description"]


def test_every_operation_documents_success_and_failure(spec: dict) -> None:
    methods = {"get", "put", "post", "delete", "patch"}
    operations = [
        (path, method, operation)
        for path, item in spec["paths"].items()
        for method, operation in item.items()
        if method in methods
    ]
    assert operations, "the document describes no operations"

    for path, method, operation in operations:
        responses = operation.get("responses", {})
        assert any(str(code).startswith("2") for code in responses), f"{method} {path}: no 2xx"
        assert any(str(code)[0] in "45" for code in responses), f"{method} {path}: no 4xx/5xx"
        assert operation.get("operationId"), f"{method} {path}: no operationId"


def test_error_envelope_is_published_and_resolvable(spec: dict) -> None:
    assert "ErrorEnvelope" in spec["components"]["schemas"]

    def refs(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "$ref" and isinstance(value, str):
                    yield value
                else:
                    yield from refs(value)
        elif isinstance(node, list):
            for item in node:
                yield from refs(item)

    for ref in refs(spec):
        node = spec
        for part in ref.removeprefix("#/").split("/"):
            assert part in node, f"unresolvable reference: {ref}"
            node = node[part]


def test_keycloak_security_scheme_is_declared(spec: dict) -> None:
    assert "KeycloakBearer" in spec["components"]["securitySchemes"]


def test_mcp_transport_is_documented(spec: dict) -> None:
    assert "/mcp" in spec["paths"]


def test_health_is_reachable_through_the_fastapi_app(client) -> None:
    assert client.get("/health").status_code == 200


def test_metrics_are_recorded_for_http_traffic(client) -> None:
    client.get("/health")
    body = client.get("/metrics").text

    assert "http_requests_total" in body
    assert 'service="tools-service"' in body
    assert 'route="/health"' in body


def test_docs_are_served_by_fastapi(client) -> None:
    response = client.get("/docs")

    assert response.status_code == 200
    assert "unpkg.com" not in response.text


def test_openapi_json_is_served_by_fastapi(client) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "Tools Service API"
