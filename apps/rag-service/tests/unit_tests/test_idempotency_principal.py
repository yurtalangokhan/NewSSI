"""Tests for the rag-service idempotency principal extractor."""

from types import SimpleNamespace

import pytest
from fastapi import Request


def _make_request(
    headers: dict[str, str] | None = None, cookies: dict[str, str] | None = None
) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/collections",
        "headers": [
            (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
        ],
        "cookies": cookies or {},
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_extracts_sub_from_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from langconnect.idempotency_principal import extract_principal_from_jwt

    monkeypatch.setattr(
        "langconnect.idempotency_principal.config",
        SimpleNamespace(
            INTERNAL_SERVICE_TOKEN="",
            KEYCLOAK_ENABLED=True,
            KEYCLOAK_ISSUER_URL="https://kc.example.com/realms/test",
        ),
    )

    def fake_decode(token: str) -> dict:
        return {"sub": "user-789", "preferred_username": "bob"}

    monkeypatch.setattr(
        "langconnect.idempotency_principal.decode_keycloak_token", fake_decode
    )

    request = _make_request({"Authorization": "Bearer some.jwt.token"})
    assert await extract_principal_from_jwt(request) == "user-789"


@pytest.mark.asyncio
async def test_returns_none_when_no_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from langconnect.idempotency_principal import extract_principal_from_jwt

    monkeypatch.setattr(
        "langconnect.idempotency_principal.config",
        SimpleNamespace(
            INTERNAL_SERVICE_TOKEN="",
            KEYCLOAK_ENABLED=True,
            KEYCLOAK_ISSUER_URL="https://kc.example.com/realms/test",
        ),
    )

    request = _make_request()
    assert await extract_principal_from_jwt(request) is None


@pytest.mark.asyncio
async def test_returns_internal_service_for_internal_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from langconnect.idempotency_principal import extract_principal_from_jwt

    monkeypatch.setattr(
        "langconnect.idempotency_principal.config",
        SimpleNamespace(
            INTERNAL_SERVICE_TOKEN="secret-token",  # noqa: S106 - test fixture
            KEYCLOAK_ENABLED=True,
            KEYCLOAK_ISSUER_URL="https://kc.example.com/realms/test",
        ),
    )

    request = _make_request({"X-Internal-Service-Token": "secret-token"})
    assert await extract_principal_from_jwt(request) == "internal-service"


@pytest.mark.asyncio
async def test_returns_none_on_invalid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from langconnect.idempotency_principal import extract_principal_from_jwt

    monkeypatch.setattr(
        "langconnect.idempotency_principal.config",
        SimpleNamespace(
            INTERNAL_SERVICE_TOKEN="",
            KEYCLOAK_ENABLED=True,
            KEYCLOAK_ISSUER_URL="https://kc.example.com/realms/test",
        ),
    )

    def fake_decode(token: str) -> dict:
        raise ValueError("invalid token")

    monkeypatch.setattr(
        "langconnect.idempotency_principal.decode_keycloak_token", fake_decode
    )

    request = _make_request({"Authorization": "Bearer bad.token"})
    assert await extract_principal_from_jwt(request) is None
