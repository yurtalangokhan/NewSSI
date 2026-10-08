"""ApplicationError can carry response headers.

Two RFC-mandated cases motivate this: a 401 must advertise how to
authenticate (RFC 7235 SS4.1, WWW-Authenticate), and a 429/503 should tell
the caller when to retry (RFC 7231 SS7.1.3, Retry-After). Neither survived to
the client before, since ApplicationError had no way to carry a header and
the FastAPI handler built the JSONResponse without one.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from error_contract import (
    ApplicationError,
    DependencyUnavailableError,
    RateLimitedError,
    UnauthorizedError,
    register_error_handlers,
)


def test_unauthorized_error_sets_www_authenticate_header():
    app = FastAPI()
    register_error_handlers(app, service_name="test-service")

    @app.get("/secret")
    async def secret():
        raise UnauthorizedError()

    response = TestClient(app).get("/secret")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_rate_limited_error_with_retry_after_sets_header():
    app = FastAPI()
    register_error_handlers(app, service_name="test-service")

    @app.get("/limited")
    async def limited():
        raise RateLimitedError(retry_after=30)

    response = TestClient(app).get("/limited")

    assert response.status_code == 429
    assert response.headers["retry-after"] == "30"


def test_dependency_unavailable_error_with_retry_after_sets_header():
    app = FastAPI()
    register_error_handlers(app, service_name="test-service")

    @app.get("/down")
    async def down():
        raise DependencyUnavailableError(retry_after=5)

    response = TestClient(app).get("/down")

    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"


def test_error_without_retry_after_has_no_retry_after_header():
    app = FastAPI()
    register_error_handlers(app, service_name="test-service")

    @app.get("/limited")
    async def limited():
        raise RateLimitedError()

    response = TestClient(app).get("/limited")

    assert "retry-after" not in response.headers


def test_application_error_custom_headers_are_forwarded():
    app = FastAPI()
    register_error_handlers(app, service_name="test-service")

    @app.get("/custom")
    async def custom():
        raise ApplicationError(
            status_code=451,
            code="content.unavailable_for_legal_reasons",
            message="Blocked.",
            headers={"X-Custom": "z"},
        )

    response = TestClient(app).get("/custom")

    assert response.status_code == 451
    assert response.headers["x-custom"] == "z"
