# ruff: noqa: S101 -- Assertions express pytest expectations.
"""Framework failures keep the shared classification and the local response shape."""

from error_contract import register_error_handlers, render_error_code_message
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from src.models import response_models
from src.models.response_errors import ErrorModel, ResponseModel, register_response_errors


def test_response_errors_share_the_local_response_models():
    assert ErrorModel is response_models.ErrorModel
    assert ResponseModel is response_models.ResponseModel


@pytest.mark.parametrize("locale", ["en", "tr"])
@pytest.mark.parametrize(
    ("status", "code"),
    [(502, "dependency.invalid_response"), (422, "validation.failed")],
)
def test_framework_error_keeps_status_code_localization_and_safe_headers(locale, status, code):
    app = FastAPI()
    register_error_handlers(app, service_name="tools-service")
    register_response_errors(app)

    @app.get("/failure")
    async def failure():
        raise HTTPException(
            status_code=status,
            detail={},
            headers={"Retry-After": "30", "X-Upstream-Secret": "private"},
        )

    response = TestClient(app).get("/failure", headers={"X-Language": locale, "X-Request-ID": "framework-test"})
    message = render_error_code_message(code, locale)
    assert response.status_code == status
    assert response.json() == {
        "statusCode": status,
        "message": message,
        "data": None,
        "error": {"code": code, "message": message, "details": None},
    }
    assert response.headers["content-language"] == locale
    assert response.headers["x-request-id"] == "framework-test"
    assert response.headers["retry-after"] == "30"
    assert "x-upstream-secret" not in response.headers
    assert int(response.headers["content-length"]) == len(response.content)


def test_operational_framework_error_keeps_native_shared_envelope():
    app = FastAPI()
    register_error_handlers(app, service_name="tools-service")
    register_response_errors(app)

    @app.get("/metrics")
    async def metrics():
        raise HTTPException(status_code=502, detail={})

    response = TestClient(app).get("/metrics", headers={"X-Language": "tr"})
    assert response.status_code == 502
    assert "statusCode" not in response.json()
    assert response.json()["error"]["code"] == "dependency.invalid_response"


def test_service_app_answers_unknown_paths_with_the_local_envelope(http_client):
    response = http_client.get("/no-such-route")

    assert response.status_code == 404
    assert response.json()["statusCode"] == 404
    assert response.json()["error"]["code"] == "request.not_found"


def test_mcp_transport_keeps_the_shared_error_envelope_in_openapi(http_client):
    responses = http_client.get("/openapi.json").json()["paths"]["/mcp"]["post"]["responses"]

    refs = {
        spec["content"]["application/json"]["schema"]["$ref"]
        for code, spec in responses.items()
        if code.isdigit() and int(code) >= 400
    }
    assert refs == {"#/components/schemas/ErrorEnvelope"}
