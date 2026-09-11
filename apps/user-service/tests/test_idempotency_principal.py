"""Tests for the user-service idempotency principal extractor."""

from types import SimpleNamespace

import pytest
from fastapi import Request


def _make_request(
    headers: dict[str, str] | None = None, cookies: dict[str, str] | None = None
) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/users/me/memories/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "cookies": cookies or {},
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope)


def test_extracts_sub_from_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.core.idempotency_principal import extract_principal_from_jwt

    monkeypatch.setattr(
        "src.core.idempotency_principal.get_settings",
        lambda: SimpleNamespace(INTERNAL_SERVICE_TOKEN="", KEYCLOAK_ENABLED=True, AUTH_SECRET="x"),
    )

    class FakeAuthService:
        async def validate_token(self, token: str) -> dict | None:
            return {"sub": "user-456"}

    monkeypatch.setattr(
        "src.core.idempotency_principal.get_auth_service",
        lambda: FakeAuthService(),
    )

    request = _make_request({"Authorization": "Bearer some.jwt.token"})
    import asyncio

    assert asyncio.run(extract_principal_from_jwt(request)) == "user-456"


def test_returns_none_when_no_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.core.idempotency_principal import extract_principal_from_jwt

    monkeypatch.setattr(
        "src.core.idempotency_principal.get_settings",
        lambda: SimpleNamespace(INTERNAL_SERVICE_TOKEN="", KEYCLOAK_ENABLED=True, AUTH_SECRET="x"),
    )

    request = _make_request()
    import asyncio

    assert asyncio.run(extract_principal_from_jwt(request)) is None


def test_returns_internal_service_for_internal_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.core.idempotency_principal import extract_principal_from_jwt

    monkeypatch.setattr(
        "src.core.idempotency_principal.get_settings",
        lambda: SimpleNamespace(
            INTERNAL_SERVICE_TOKEN="secret-token", KEYCLOAK_ENABLED=True, AUTH_SECRET="x"
        ),
    )

    request = _make_request({"X-Internal-Service-Token": "secret-token"})
    import asyncio

    assert asyncio.run(extract_principal_from_jwt(request)) == "internal-service"


def test_returns_dev_user_in_dev_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.core.idempotency_principal import extract_principal_from_jwt

    monkeypatch.setattr(
        "src.core.idempotency_principal.get_settings",
        lambda: SimpleNamespace(
            INTERNAL_SERVICE_TOKEN="", KEYCLOAK_ENABLED=False, AUTH_SECRET=None
        ),
    )

    class FakeAuthService:
        async def validate_token(self, token: str) -> dict | None:
            return None

    monkeypatch.setattr(
        "src.core.idempotency_principal.get_auth_service",
        lambda: FakeAuthService(),
    )

    request = _make_request({"Authorization": "Bearer some.token"})
    import asyncio

    assert asyncio.run(extract_principal_from_jwt(request)) == "dev-user"
