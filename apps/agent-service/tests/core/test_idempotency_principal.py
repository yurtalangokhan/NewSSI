"""Tests for the agent-service idempotency principal extractor."""

import asyncio

from fastapi import Request
import pytest

SECRET = "secret-token"


def _make_request(headers: dict[str, str] | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat/messages",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope)


def _with_secret(monkeypatch: pytest.MonkeyPatch, secret: str) -> None:
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", secret)


def test_extracts_subject_from_gateway_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.http.idempotency_principal import extract_principal_from_jwt

    _with_secret(monkeypatch, SECRET)
    request = _make_request({"x-gateway-token": SECRET, "x-gateway-user-id": "user-123"})

    assert asyncio.run(extract_principal_from_jwt(request)) == "user-123"


def test_returns_none_when_request_skipped_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.http.idempotency_principal import extract_principal_from_jwt

    _with_secret(monkeypatch, SECRET)
    request = _make_request({"Authorization": "Bearer some.jwt.token"})

    assert asyncio.run(extract_principal_from_jwt(request)) is None


def test_returns_none_when_no_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.http.idempotency_principal import extract_principal_from_jwt

    _with_secret(monkeypatch, SECRET)

    assert asyncio.run(extract_principal_from_jwt(_make_request())) is None


def test_returns_internal_service_for_internal_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.http.idempotency_principal import extract_principal_from_jwt

    _with_secret(monkeypatch, SECRET)
    request = _make_request({"X-Internal-Service-Token": SECRET})

    assert asyncio.run(extract_principal_from_jwt(request)) == "internal-service"


def test_internal_delegation_scopes_to_delegated_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two users delegated through one machine credential must not share a scope."""
    from core.http.idempotency_principal import extract_principal_from_jwt

    _with_secret(monkeypatch, SECRET)
    request = _make_request({"X-Internal-Service-Token": SECRET, "X-User-Id": "user-9"})

    assert asyncio.run(extract_principal_from_jwt(request)) == "user-9"
