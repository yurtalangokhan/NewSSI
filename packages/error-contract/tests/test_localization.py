import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, field_validator

from error_contract import (
    ApplicationError,
    ConfigurationError,
    DatabaseConnectionError,
    DatabaseOperationError,
    DatabaseTimeoutError,
    DependencyAuthenticationError,
    DependencyRateLimitedError,
    DependencyResponseError,
    DependencyTimeoutError,
    DependencyUnavailableError,
    InternalServerError,
    OperationExecutionError,
    OperationTimeoutError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
    register_error_handlers,
    render_error_code_message,
    render_error_message,
)
from error_contract.starlette import ErrorContractMiddleware


@pytest.mark.parametrize(
    ("error_type", "status_code", "code"),
    [
        (DatabaseConnectionError, 503, "database.connection_failed"),
        (DatabaseTimeoutError, 503, "database.timeout"),
        (DatabaseOperationError, 500, "database.operation_failed"),
        (DependencyTimeoutError, 504, "dependency.timeout"),
        (DependencyResponseError, 502, "dependency.invalid_response"),
        (DependencyAuthenticationError, 502, "dependency.authentication_failed"),
        (DependencyRateLimitedError, 503, "dependency.rate_limited"),
        (ConfigurationError, 500, "configuration.invalid"),
        (PayloadTooLargeError, 413, "request.payload_too_large"),
        (UnsupportedMediaTypeError, 415, "request.unsupported_media_type"),
        (OperationTimeoutError, 504, "operation.timeout"),
        (OperationExecutionError, 500, "operation.failed"),
        (InternalServerError, 500, "internal.server_error"),
    ],
)
def test_builtin_error_defaults(error_type, status_code, code):
    error = error_type()

    assert error.status_code == status_code
    assert error.code == code
    assert error.message_key == f"errors.{code}"
    assert error.message_params == {}


@pytest.mark.parametrize(
    "error_type",
    [
        DatabaseConnectionError,
        DatabaseTimeoutError,
        DependencyTimeoutError,
        DependencyResponseError,
        DependencyAuthenticationError,
        DependencyRateLimitedError,
    ],
)
def test_unavailable_error_types_share_dependency_catch_semantics(error_type):
    assert issubclass(error_type, DependencyUnavailableError)


def test_renderer_translates_shared_defaults_without_mutating_the_error():
    error = DatabaseConnectionError()

    assert render_error_message(error, locale="en") == "Database connection failed."
    assert render_error_message(error, locale="tr-TR") == "Veritabanı bağlantısı başarısız oldu."
    assert error.message == "Database connection failed."


def test_explicit_legacy_message_without_key_remains_unchanged():
    error = DatabaseConnectionError(message="The primary database is offline.")

    assert error.message_key is None
    assert render_error_message(error, locale="tr") == "The primary database is offline."


def test_legacy_subclass_default_message_without_declared_key_remains_unchanged():
    class LegacyDomainError(ApplicationError):
        code = "domain.legacy"
        message = "Legacy domain message."

    error = LegacyDomainError()

    assert error.message_key is None
    assert render_error_message(error, locale="tr") == "Legacy domain message."


def test_subclass_inherits_parent_key_when_it_keeps_the_parent_default_message():
    class DomainDatabaseError(DatabaseConnectionError):
        code = "domain.database_unavailable"

    error = DomainDatabaseError()

    assert error.message_key == "errors.database.connection_failed"
    assert render_error_message(error, locale="tr") == "Veritabanı bağlantısı başarısız oldu."


def test_renderer_interpolates_safe_parameters_and_falls_back_on_invalid_parameters():
    valid = ApplicationError(
        message="Invalid value.",
        message_key="errors.validation.string_too_short",
        message_params={"min_length": 3},
    )
    invalid = ApplicationError(
        message="Invalid value.",
        message_key="errors.validation.string_too_short",
    )

    assert render_error_message(valid, locale="en") == "Must contain at least 3 characters."
    assert render_error_message(valid, locale="tr") == "En az 3 karakter içermelidir."
    assert render_error_message(invalid, locale="tr") == "Invalid value."


def test_known_code_renderer_never_returns_unknown_keys():
    assert render_error_code_message("dependency.timeout", locale="tr") == (
        "Bağımlılık zaman aşımına uğradı."
    )
    assert render_error_code_message("not.a.known.code", locale="tr") == (
        "Beklenmeyen bir hata oluştu."
    )


def _localized_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app, service_name="test-service")

    @app.get("/typed")
    async def typed():
        raise DatabaseTimeoutError()

    @app.get("/unknown")
    async def unknown():
        raise RuntimeError("database password leaked")

    @app.get("/limited")
    async def limited():
        raise HTTPException(
            status_code=429,
            detail={},
            headers={
                "Retry-After": "30",
                "WWW-Authenticate": 'Bearer realm="api"',
                "X-Upstream-Secret": "hidden",
            },
        )

    class Payload(BaseModel):
        name: str
        age: int | None = None

        @field_validator("age")
        @classmethod
        def validate_age(cls, value):
            if value == 13:
                raise ValueError("secret validation implementation detail")
            return value

    @app.post("/payload")
    async def payload(body: Payload):
        return body

    return app


def test_handlers_render_typed_validation_and_unknown_errors_in_request_locale():
    client = TestClient(_localized_app(), raise_server_exceptions=False)

    typed = client.get("/typed", headers={"Accept-Language": "tr-TR,tr;q=0.9"})
    missing = client.post("/payload?lang=tr", json={})
    invalid = client.post("/payload", headers={"X-Language": "tr"}, json={"name": "x", "age": 13})
    unknown = client.get("/unknown", headers={"X-Language": "tr"})

    assert typed.json()["error"]["message"] == "Veritabanı işlemi zaman aşımına uğradı."
    assert typed.headers["content-language"] == "tr"
    assert missing.json()["error"]["message"] == "İstek doğrulaması başarısız oldu."
    assert missing.json()["error"]["field_errors"] == [
        {"field": "body.name", "code": "missing", "message": "Alan gerekli"}
    ]
    assert invalid.json()["error"]["field_errors"] == [
        {"field": "body.age", "code": "value_error", "message": "Geçersiz değer."}
    ]
    assert "secret validation" not in invalid.text
    assert unknown.json()["error"]["message"] == "Beklenmeyen bir hata oluştu."
    assert unknown.headers["content-language"] == "tr"


def test_http_exception_preserves_only_allowed_headers_and_localizes_fallback():
    response = TestClient(_localized_app()).get("/limited", headers={"X-Language": "tr"})

    assert response.status_code == 429
    assert response.json()["error"]["message"] == "Çok fazla istek. Daha sonra tekrar deneyin."
    assert response.headers["retry-after"] == "30"
    assert response.headers["www-authenticate"] == 'Bearer realm="api"'
    assert "x-upstream-secret" not in response.headers
    assert response.headers["content-language"] == "tr"


def test_concurrent_requests_keep_locales_isolated():
    client = TestClient(_localized_app())

    def request(locale: str) -> tuple[str, str]:
        response = client.get("/typed", headers={"X-Language": locale})
        return response.headers["content-language"], response.json()["error"]["message"]

    with ThreadPoolExecutor(max_workers=2) as executor:
        english = executor.submit(request, "en")
        turkish = executor.submit(request, "tr")

    assert english.result() == ("en", "Database operation timed out.")
    assert turkish.result() == ("tr", "Veritabanı işlemi zaman aşımına uğradı.")


def test_starlette_fallback_does_not_start_a_second_response_after_start():
    starts: list[dict] = []

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise RuntimeError("stream failed")

    async def send(message):
        if message["type"] == "http.response.start":
            starts.append(message)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/stream",
        "raw_path": b"/stream",
        "query_string": b"",
        "headers": [],
        "client": ("test", 1),
        "server": ("test", 80),
    }
    middleware = ErrorContractMiddleware(app, service_name="test-service")

    with pytest.raises(RuntimeError, match="stream failed"):
        asyncio.run(middleware(scope, receive, send))

    assert len(starts) == 1


def test_inherited_legacy_message_stays_literal_across_multiple_levels():
    class LegacyError(ApplicationError):
        message = "Legacy public message"

    class ChildError(LegacyError):
        pass

    assert render_error_message(ChildError(), "tr") == "Legacy public message"


def test_router_default_not_found_is_localized():
    response = TestClient(_localized_app()).get("/missing", headers={"X-Language": "tr"})
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Kaynak bulunamadı."
