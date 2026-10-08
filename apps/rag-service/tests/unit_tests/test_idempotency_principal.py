"""Tests for the rag-service idempotency principal extractor."""

from types import SimpleNamespace

import pytest

from src.shared import idempotency_principal

SECRET = "secret-token"


def _request(headers: dict[str, str] | None = None):
    return SimpleNamespace(
        headers=headers or {},
        cookies={},
        client=SimpleNamespace(host="127.0.0.1"),
    )


def _with_secret(monkeypatch: pytest.MonkeyPatch, secret: str) -> None:
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", secret)


async def test_extracts_subject_from_gateway_identity(monkeypatch: pytest.MonkeyPatch):
    _with_secret(monkeypatch, SECRET)
    request = _request({"x-gateway-token": SECRET, "x-gateway-user-id": "user-123"})

    assert await idempotency_principal.extract_principal_from_jwt(request) == "user-123"


async def test_returns_none_when_request_skipped_gateway(
    monkeypatch: pytest.MonkeyPatch,
):
    _with_secret(monkeypatch, SECRET)
    request = _request({"authorization": "Bearer some.jwt.token"})

    assert await idempotency_principal.extract_principal_from_jwt(request) is None


async def test_returns_none_without_headers(monkeypatch: pytest.MonkeyPatch):
    _with_secret(monkeypatch, SECRET)

    assert await idempotency_principal.extract_principal_from_jwt(_request()) is None


async def test_returns_internal_service_for_internal_token(
    monkeypatch: pytest.MonkeyPatch,
):
    _with_secret(monkeypatch, SECRET)
    request = _request({"x-internal-service-token": SECRET})

    assert (
        await idempotency_principal.extract_principal_from_jwt(request)
        == "internal-service"
    )


async def test_internal_delegation_scopes_to_delegated_user(
    monkeypatch: pytest.MonkeyPatch,
):
    """Two users delegated through one machine credential must not share a scope."""
    _with_secret(monkeypatch, SECRET)
    request = _request({"x-internal-service-token": SECRET, "x-user-id": "user-9"})

    assert await idempotency_principal.extract_principal_from_jwt(request) == "user-9"
