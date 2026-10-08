"""Tools-service accepts only callers Gateway has already authenticated."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.core import auth

SECRET = "shared-gateway-secret"


def _settings() -> SimpleNamespace:
    return SimpleNamespace(MCP_PUBLIC_BASE_URL="http://localhost:9000/mcp")


def _gateway_headers(**overrides: str) -> dict[str, str]:
    headers = {
        "x-gateway-token": SECRET,
        "x-gateway-user-id": "keycloak-sub-1",
        "x-gateway-email": "ada@example.com",
        "x-gateway-username": "ada",
        "x-gateway-roles": "enduser",
    }
    headers.update(overrides)
    return headers


def _configure(monkeypatch, headers: dict[str, str], secret: str = SECRET) -> None:
    monkeypatch.setattr(auth, "env", _settings())
    monkeypatch.setattr(auth, "_get_internal_service_token", lambda: secret)
    monkeypatch.setattr(auth, "get_http_headers", lambda include_all=False: headers)


async def test_accepts_gateway_authenticated_user(monkeypatch) -> None:
    _configure(monkeypatch, _gateway_headers())
    monkeypatch.setattr(
        auth, "get_user_service_permissions", AsyncMock(return_value=["tool:execute"])
    )

    result = await auth.GatewayTokenVerifier().verify_token("forwarded-user-token")

    assert result is not None
    assert result.client_id == "keycloak-sub-1"
    assert result.scopes == ["tool:execute"]
    assert result.claims["email"] == "ada@example.com"
    assert result.claims["iss"] == "gateway"


async def test_rejects_bare_keycloak_token(monkeypatch) -> None:
    """A valid user JWT that did not come through Gateway is not accepted."""
    _configure(monkeypatch, {"authorization": "Bearer real.jwt.token"})

    assert await auth.GatewayTokenVerifier().verify_token("real.jwt.token") is None


async def test_rejects_forged_identity_headers(monkeypatch) -> None:
    headers = _gateway_headers()
    headers.pop("x-gateway-token")
    _configure(monkeypatch, headers)

    assert await auth.GatewayTokenVerifier().verify_token("anything") is None


async def test_accepts_internal_service_token(monkeypatch) -> None:
    _configure(monkeypatch, {"x-internal-service-token": SECRET})

    result = await auth.GatewayTokenVerifier().verify_token(SECRET)

    assert result is not None
    assert result.client_id == "internal-service"
    assert result.claims["internal"] is True


async def test_internal_delegation_uses_delegated_subject(monkeypatch) -> None:
    _configure(monkeypatch, {"x-internal-service-token": SECRET, "x-user-id": "user-9"})

    result = await auth.GatewayTokenVerifier().verify_token(SECRET)

    assert result is not None
    assert result.client_id == "user-9"


async def test_fails_closed_without_configured_secret(monkeypatch) -> None:
    _configure(monkeypatch, _gateway_headers(), secret="")

    assert await auth.GatewayTokenVerifier().verify_token("anything") is None
