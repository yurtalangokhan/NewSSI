"""User-service accepts only identity authenticated by Gateway."""

from types import SimpleNamespace

import pytest
from fastapi import Request

from src.api import dependencies
from src.core import idempotency_principal
from src.service.auth_service import AuthService
from src.service.keycloak_service import KeycloakService


def _request(headers: dict[str, str]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/auth/me",
            "headers": [(name.lower().encode(), value.encode()) for name, value in headers.items()],
        }
    )


@pytest.mark.asyncio
async def test_gateway_identity_authenticates_me_without_validating_bearer(monkeypatch):
    monkeypatch.setattr(
        dependencies, "env", SimpleNamespace(INTERNAL_SERVICE_TOKEN="gateway-proof")
    )
    request = _request(
        {
            "x-gateway-token": "gateway-proof",
            "x-gateway-user-id": "demo2-id",
            "authorization": "Bearer token-validated-by-gateway",
        }
    )

    assert await dependencies.get_current_user_id(request) == "demo2-id"


@pytest.mark.asyncio
async def test_bearer_or_forged_gateway_headers_do_not_authenticate(monkeypatch):
    monkeypatch.setattr(
        dependencies, "env", SimpleNamespace(INTERNAL_SERVICE_TOKEN="gateway-proof")
    )
    for headers in (
        {"authorization": "Bearer arbitrary"},
        {"x-gateway-user-id": "victim"},
        {"x-gateway-token": "wrong", "x-gateway-user-id": "victim"},
        {"x-gateway-token": "gateway-proof"},
    ):
        assert await dependencies.get_current_user_id(_request(headers)) is None


@pytest.mark.asyncio
async def test_idempotency_principal_uses_same_gateway_identity(monkeypatch):
    monkeypatch.setattr(
        idempotency_principal,
        "env",
        SimpleNamespace(INTERNAL_SERVICE_TOKEN="gateway-proof"),
    )
    request = _request(
        {
            "x-gateway-token": "gateway-proof",
            "x-gateway-user-id": "demo2-id",
        }
    )
    assert await idempotency_principal.extract_principal_from_gateway(request) == "demo2-id"
    assert (
        await idempotency_principal.extract_principal_from_gateway(
            _request({"authorization": "Bearer arbitrary"})
        )
        is None
    )


def test_user_service_does_not_expose_token_validation() -> None:
    assert not hasattr(AuthService, "validate_token")
    assert not hasattr(KeycloakService, "validate_token_jwks")
