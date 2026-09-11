from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.applications import Starlette
from starlette.routing import Route

from error_contract import (
    ApplicationError,
    ConflictError,
    ErrorContractMiddleware,
    ErrorEnvelope,
    FieldError,
    register_error_handlers,
)


def test_error_envelope_serializes_with_stable_shape():
    envelope = ErrorEnvelope.from_error(
        code="collection.not_found",
        message="Collection not found.",
        details={"collection_id": "abc"},
        field_errors=[FieldError(field="name", code="required", message="Name is required.")],
        request_id="req_123",
    )

    assert envelope.model_dump() == {
        "error": {
            "code": "collection.not_found",
            "message": "Collection not found.",
            "details": {"collection_id": "abc"},
            "field_errors": [
                {"field": "name", "code": "required", "message": "Name is required."}
            ],
            "request_id": "req_123",
        }
    }


def test_application_error_handler_returns_standard_contract():
    app = FastAPI()
    register_error_handlers(app, service_name="test-service")

    @app.get("/conflict")
    async def conflict():
        raise ConflictError(
            code="organization.root_exists",
            message="A root organization already exists",
            details={"scope": "root"},
        )

    response = TestClient(app).get("/conflict", headers={"X-Request-ID": "req_abc"})

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "organization.root_exists",
            "message": "A root organization already exists",
            "details": {"scope": "root"},
            "field_errors": [],
            "request_id": "req_abc",
        }
    }


def test_http_exception_handler_normalizes_detail_payloads():
    app = FastAPI()
    register_error_handlers(app, service_name="test-service")

    @app.get("/legacy")
    async def legacy():
        raise HTTPException(status_code=404, detail="Missing thing")

    response = TestClient(app).get("/legacy")

    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "request.not_found",
        "message": "Missing thing",
        "details": {},
        "field_errors": [],
        "request_id": None,
    }


def test_http_exception_handler_hides_legacy_5xx_details():
    app = FastAPI()
    register_error_handlers(app, service_name="test-service")

    @app.get("/legacy-500")
    async def legacy_500():
        raise HTTPException(status_code=500, detail="database password leaked")

    response = TestClient(app).get("/legacy-500")

    assert response.status_code == 500
    assert response.json()["error"] == {
        "code": "internal.server_error",
        "message": "An unexpected error occurred.",
        "details": {},
        "field_errors": [],
        "request_id": None,
    }
    assert "database password leaked" not in response.text


def test_validation_errors_become_field_errors():
    app = FastAPI()
    register_error_handlers(app, service_name="test-service")

    class Payload(BaseModel):
        name: str

    @app.post("/payload")
    async def payload(body: Payload):
        return body

    response = TestClient(app).post("/payload", json={})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation.failed"
    assert body["error"]["message"] == "Request validation failed."
    assert body["error"]["field_errors"] == [
        {"field": "body.name", "code": "missing", "message": "Field required"}
    ]


def test_unhandled_errors_are_safe_and_logged(caplog):
    app = FastAPI()
    register_error_handlers(app, service_name="test-service")

    @app.get("/boom")
    async def boom():
        raise RuntimeError("database password leaked")

    response = TestClient(app, raise_server_exceptions=False).get("/boom")

    assert response.status_code == 500
    assert response.json()["error"] == {
        "code": "internal.server_error",
        "message": "An unexpected error occurred.",
        "details": {},
        "field_errors": [],
        "request_id": None,
    }
    assert "Unhandled test-service request failed" in caplog.text
    assert "GET /boom" in caplog.text
    assert "internal.server_error" in caplog.text
    assert "database password leaked" not in caplog.text
    assert "database password leaked" not in response.text


def test_application_error_defaults_are_explicit():
    error = ApplicationError(status_code=418, code="teapot.short", message="Too short.")

    assert error.status_code == 418
    assert error.code == "teapot.short"
    assert error.message == "Too short."
    assert error.details == {}
    assert error.field_errors == []


def test_starlette_middleware_normalizes_unhandled_errors():
    async def boom(_request):
        raise RuntimeError("secret provider token")

    app = Starlette(routes=[Route("/boom", boom)])
    app.add_middleware(ErrorContractMiddleware, service_name="test-starlette")

    response = TestClient(app, raise_server_exceptions=False).get("/boom")

    assert response.status_code == 500
    assert response.json()["error"] == {
        "code": "internal.server_error",
        "message": "An unexpected error occurred.",
        "details": {},
        "field_errors": [],
        "request_id": None,
    }
    assert "secret provider token" not in response.text
