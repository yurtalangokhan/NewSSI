"""Tests for the agent-service idempotency principal extractor."""

from types import SimpleNamespace

import pytest
from fastapi import Request


def _make_request(
    headers: dict[str, str] | None = None, cookies: dict[str, str] | None = None
) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat/send-chat-message",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "cookies": cookies or {},
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope)


def test_extracts_sub_from_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.idempotency_principal import extract_principal_from_jwt

    monkeypatch.setattr(
        "core.idempotency_principal.settings",
        SimpleNamespace(INTERNAL_SERVICE_TOKEN="", KEYCLOAK_ENABLED=True),
    )

    class FakeAuthService:
        @staticmethod
        def is_keycloak_enabled() -> bool:
            return True

        @staticmethod
        def decode_keycloak_token(token: str) -> dict:
            return {"sub": "user-123", "preferred_username": "alice"}

    monkeypatch.setattr("core.idempotency_principal.AuthService", FakeAuthService)

    request = _make_request({"Authorization": "Bearer some.jwt.token"})
    import asyncio

    assert asyncio.run(extract_principal_from_jwt(request)) == "user-123"


def test_returns_none_when_no_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.idempotency_principal import extract_principal_from_jwt

    monkeypatch.setattr(
        "core.idempotency_principal.settings",
        SimpleNamespace(INTERNAL_SERVICE_TOKEN="", KEYCLOAK_ENABLED=True),
    )

    request = _make_request()
    import asyncio

    assert asyncio.run(extract_principal_from_jwt(request)) is None


def test_returns_internal_service_for_internal_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.idempotency_principal import extract_principal_from_jwt

    monkeypatch.setattr(
        "core.idempotency_principal.settings",
        SimpleNamespace(INTERNAL_SERVICE_TOKEN="secret-token", KEYCLOAK_ENABLED=True),
    )

    request = _make_request({"X-Internal-Service-Token": "secret-token"})
    import asyncio

    assert asyncio.run(extract_principal_from_jwt(request)) == "internal-service"


def test_returns_none_on_invalid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.idempotency_principal import extract_principal_from_jwt

    monkeypatch.setattr(
        "core.idempotency_principal.settings",
        SimpleNamespace(INTERNAL_SERVICE_TOKEN="", KEYCLOAK_ENABLED=True),
    )

    class FakeAuthService:
        @staticmethod
        def is_keycloak_enabled() -> bool:
            return True

        @staticmethod
        def decode_keycloak_token(token: str) -> dict:
            raise ValueError("invalid token")

    monkeypatch.setattr("core.idempotency_principal.AuthService", FakeAuthService)

    request = _make_request({"Authorization": "Bearer bad.token"})
    import asyncio

    assert asyncio.run(extract_principal_from_jwt(request)) is None
