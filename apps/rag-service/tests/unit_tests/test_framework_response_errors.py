# ruff: noqa: S101 -- Assertions express pytest expectations.
"""Framework failures preserve the shared classification and local response shape."""

from error_contract import register_error_handlers, render_error_code_message
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from src.shared.response_errors import register_response_errors


@pytest.mark.parametrize("locale", ["en", "tr"])
@pytest.mark.parametrize(
    ("status", "detail", "code"),
    [
        (502, {}, "dependency.invalid_response"),
        (422, {}, "validation.failed"),
        (502, {"code": "dependency.timeout", "message": "private upstream diagnostic"}, "dependency.invalid_response"),
        (
            403,
            {"error": {"code": "collection.access_denied", "message": "Collection access denied."}},
            "collection.access_denied",
        ),
        (422, {"code": "domain.input_invalid", "message": "Invalid supplied value."}, "domain.input_invalid"),
    ],
)
def test_framework_error_keeps_status_code_localization_and_safe_headers(locale, status, detail, code):
    app = FastAPI()
    register_error_handlers(app, service_name="rag-service")
    register_response_errors(app)

    @app.get("/failure")
    async def failure():
        raise HTTPException(
            status_code=status,
            detail=detail,
            headers={
                "Retry-After": "30",
                "WWW-Authenticate": "Bearer",
                "X-Upstream-Secret": "private",
            },
        )

    response = TestClient(app).get("/failure", headers={"X-Language": locale, "X-Request-ID": "framework-test"})
    if status < 500 and detail:
        message = detail.get("error", detail)["message"]
    else:
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
    assert response.headers["www-authenticate"] == "Bearer"
    assert "x-upstream-secret" not in response.headers
    assert int(response.headers["content-length"]) == len(response.content)


def test_operational_framework_error_keeps_native_shared_envelope():
    app = FastAPI()
    register_error_handlers(app, service_name="rag-service")
    register_response_errors(app)

    @app.get("/metrics")
    async def metrics():
        raise HTTPException(status_code=502, detail={})

    response = TestClient(app).get("/metrics", headers={"X-Language": "tr"})
    assert response.status_code == 502
    assert "statusCode" not in response.json()
    assert response.json()["error"]["code"] == "dependency.invalid_response"
    assert response.json()["error"]["message"] == render_error_code_message("dependency.invalid_response", "tr")


def test_response_models_live_in_shared_beside_response_errors():
    from src.shared import response_errors, response_models

    assert response_errors.ResponseModel is response_models.ResponseModel
    assert response_errors.ErrorModel is response_models.ErrorModel
