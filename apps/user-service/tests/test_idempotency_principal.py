"""User-service idempotency uses the same Gateway identity as route auth."""

from types import SimpleNamespace

import pytest
from fastapi import Request

from src.core import idempotency_principal


def _request(headers: dict[str, str] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/users/me/memories/",
            "headers": [
                (name.lower().encode(), value.encode())
                for name, value in (headers or {}).items()
            ],
        }
    )


@pytest.mark.asyncio
async def test_gateway_subject_scopes_idempotency(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        idempotency_principal,
        "env",
        SimpleNamespace(INTERNAL_SERVICE_TOKEN="secret-token"),
    )
    request = _request(
        {"x-gateway-token": "secret-token", "x-gateway-user-id": "user-456"}
    )
    assert await idempotency_principal.extract_principal_from_gateway(request) == "user-456"


@pytest.mark.asyncio
async def test_bearer_token_alone_has_no_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        idempotency_principal,
        "env",
        SimpleNamespace(INTERNAL_SERVICE_TOKEN="secret-token"),
    )
    request = _request({"authorization": "Bearer some.jwt.token"})
    assert await idempotency_principal.extract_principal_from_gateway(request) is None


@pytest.mark.asyncio
async def test_internal_service_token_scopes_machine_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        idempotency_principal,
        "env",
        SimpleNamespace(INTERNAL_SERVICE_TOKEN="secret-token"),
    )
    request = _request({"x-internal-service-token": "secret-token"})
    assert (
        await idempotency_principal.extract_principal_from_gateway(request)
        == "internal-service"
    )


@pytest.mark.asyncio
async def test_missing_or_wrong_proof_has_no_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        idempotency_principal,
        "env",
        SimpleNamespace(INTERNAL_SERVICE_TOKEN="secret-token"),
    )
    assert await idempotency_principal.extract_principal_from_gateway(_request()) is None
    request = _request({"x-gateway-token": "wrong", "x-gateway-user-id": "victim"})
    assert await idempotency_principal.extract_principal_from_gateway(request) is None
