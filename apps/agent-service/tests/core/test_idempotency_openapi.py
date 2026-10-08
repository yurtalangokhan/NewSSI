"""The generated OpenAPI must declare the idempotency contract.

The middleware short-circuits mutating requests before any route runs, so the
only place a client can learn what it returns is the spec. These tests drive
the real application object and assert on the generated document.
"""

from fastapi.testclient import TestClient

from app import app

#: agent-service answers every error with its ResponseModel envelope.
ERROR_SCHEMA = "AgentServiceErrorResponse"


def _spec() -> dict:
    return TestClient(app).get("/openapi.json").json()


def _mutating_operations(spec: dict) -> dict:
    return {
        f"{method.upper()} {path}": operation
        for path, item in spec["paths"].items()
        for method in ("post", "put", "patch", "delete")
        if isinstance(item.get(method), dict)
        for operation in (item[method],)
    }


def test_mutating_operations_declare_the_idempotency_key_header() -> None:
    spec = _spec()
    operations = _mutating_operations(spec)

    assert operations, "the service must expose mutating operations"
    missing = [
        name
        for name, operation in operations.items()
        if not any(
            parameter.get("name") == "Idempotency-Key"
            for parameter in operation.get("parameters", [])
        )
    ]
    assert missing == [], f"Idempotency-Key header missing on: {missing[:3]}"


def test_mutating_operations_declare_the_replayed_response_header() -> None:
    spec = _spec()
    operations = _mutating_operations(spec)

    missing = [
        name
        for name, operation in operations.items()
        if not any(
            "Idempotency-Replayed" in (response.get("headers") or {})
            for response in (operation.get("responses") or {}).values()
        )
    ]
    assert missing == [], f"Idempotency-Replayed header missing on: {missing[:3]}"


def test_middleware_error_codes_are_described_on_their_status_codes() -> None:
    spec = _spec()
    operations = _mutating_operations(spec)

    expected = {
        "400": "idempotency_key_required",
        "409": "idempotency_key_reused",
        "425": "idempotency_request_in_progress",
        "503": "idempotency_store_unavailable",
    }
    for name, operation in operations.items():
        responses = operation.get("responses") or {}
        for code, needle in expected.items():
            description = responses.get(code, {}).get("description", "")
            assert needle in description, f"{name} {code} must describe {needle}"


def test_error_envelope_schema_resolves_on_idempotency_statuses() -> None:
    """The 4xx/5xx entries reference the service's error schema from components; a
    dangling ref would break every OpenAPI consumer, not just the docs."""
    spec = _spec()
    components = (spec.get("components") or {}).get("schemas") or {}
    assert ERROR_SCHEMA in components

    operations = _mutating_operations(spec)
    for name, operation in operations.items():
        for code in ("400", "409", "425", "503"):
            content = (operation.get("responses") or {}).get(code, {}).get("content") or {}
            schema = content.get("application/json", {}).get("schema") or {}
            assert schema.get("$ref") == f"#/components/schemas/{ERROR_SCHEMA}", (
                f"{name} {code} must reference the resolved {ERROR_SCHEMA}"
            )
