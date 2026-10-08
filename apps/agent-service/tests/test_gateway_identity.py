"""Gateway-authenticated identity replaces local token verification."""

import pytest
from starlette.requests import Request

import api.dependencies as api_dependencies
from core.exceptions import UnauthorizedError
from security import resolve_gateway_identity

SECRET = "shared-gateway-secret"


def _request(headers: dict[str, str]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/me",
            "headers": [
                (key.encode(), value.encode()) for key, value in headers.items()
            ],
        }
    )


def _gateway_headers(**overrides: str) -> dict[str, str]:
    headers = {
        "x-gateway-token": SECRET,
        "x-gateway-user-id": "keycloak-sub-1",
        "x-gateway-email": "ada@example.com",
        "x-gateway-username": "ada",
        "x-gateway-roles": "enduser,agent-user",
        "authorization": "Bearer forwarded-user-token",
    }
    headers.update(overrides)
    return headers


# --------------------------------------------------------------------------
# Pure resolver
# --------------------------------------------------------------------------


def test_resolver_accepts_gateway_identity():
    identity = resolve_gateway_identity(_gateway_headers(), SECRET)

    assert identity is not None
    assert identity.user_id == "keycloak-sub-1"
    assert identity.email == "ada@example.com"
    assert identity.username == "ada"
    assert identity.roles == ("enduser", "agent-user")
    assert identity.is_internal is False


def test_resolver_rejects_forged_identity_without_secret():
    headers = _gateway_headers()
    headers.pop("x-gateway-token")

    assert resolve_gateway_identity(headers, SECRET) is None


def test_resolver_rejects_wrong_secret():
    assert resolve_gateway_identity(_gateway_headers(**{"x-gateway-token": "nope"}), SECRET) is None


def test_resolver_rejects_gateway_token_without_user_id():
    headers = _gateway_headers()
    headers.pop("x-gateway-user-id")

    assert resolve_gateway_identity(headers, SECRET) is None


def test_resolver_fails_closed_when_secret_unset():
    assert resolve_gateway_identity(_gateway_headers(), "") is None
    assert resolve_gateway_identity(_gateway_headers(), None) is None


def test_resolver_accepts_internal_service_token():
    identity = resolve_gateway_identity({"x-internal-service-token": SECRET}, SECRET)

    assert identity is not None
    assert identity.is_internal is True
    assert identity.user_id == "internal-service"


def test_resolver_carries_internal_delegation():
    identity = resolve_gateway_identity(
        {"x-internal-service-token": SECRET, "x-user-id": "delegated-1"},
        SECRET,
    )

    assert identity is not None
    assert identity.delegated_user_id == "delegated-1"


def test_resolver_rejects_bare_bearer_token():
    """A valid Keycloak token alone is not authentication any more."""
    assert resolve_gateway_identity({"authorization": "Bearer real.jwt.token"}, SECRET) is None


# --------------------------------------------------------------------------
# FastAPI dependency
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_require_user_builds_user_from_gateway_headers(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", str(SECRET))

    user = await api_dependencies.require_user(_request(_gateway_headers()))

    assert user.user_id == "keycloak-sub-1"
    assert user.email == "ada@example.com"
    assert user.username == "ada"
    assert user.roles == ["enduser", "agent-user"]
    assert user.access_token == "forwarded-user-token"
    assert user.claims["gateway_authenticated"] is True


@pytest.mark.asyncio
async def test_require_user_rejects_request_that_skipped_gateway(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", str(SECRET))

    with pytest.raises(UnauthorizedError):
        await api_dependencies.require_user(
            _request({"authorization": "Bearer real.jwt.token"})
        )


@pytest.mark.asyncio
async def test_require_user_rejects_forged_gateway_user_id(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", str(SECRET))
    headers = _gateway_headers()
    headers.pop("x-gateway-token")

    with pytest.raises(UnauthorizedError):
        await api_dependencies.require_user(_request(headers))


@pytest.mark.asyncio
async def test_require_user_accepts_internal_service_token(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", str(SECRET))

    user = await api_dependencies.require_user(
        _request({"x-internal-service-token": SECRET})
    )

    assert user.user_id == "internal-service"
    assert user.roles == ["internal"]
    assert user.access_token is None


@pytest.mark.asyncio
async def test_require_user_has_no_dev_fallback(monkeypatch):
    """With no secret configured the service fails closed, never dev-user."""
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", str(""))

    with pytest.raises(UnauthorizedError):
        await api_dependencies.require_user(_request(_gateway_headers()))
