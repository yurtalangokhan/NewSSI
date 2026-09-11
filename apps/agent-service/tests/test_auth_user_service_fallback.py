from unittest.mock import AsyncMock

import pytest
from starlette.requests import Request

import api.dependencies as api_dependencies
from core.exceptions import UnauthorizedError
from service import AuthService
from service.AuthService import require_user, require_user_or_internal_service_token


def test_has_permission_reads_only_legacy_permissions_claim(monkeypatch):
    monkeypatch.setattr(AuthService.settings, "KEYCLOAK_CLIENT_ID", "agenticai-web")

    assert AuthService.AuthService.has_permission(
        {"permissions": ["agent:invoke"]},
        "agent:invoke",
    )
    assert not AuthService.AuthService.has_permission(
        {"resource_access": {"agenticai-web": {"roles": ["thread:create"]}}},
        "thread:create",
    )
    assert not AuthService.AuthService.has_permission(
        {"realm_access": {"roles": ["*"]}},
        "agent:delete",
    )


def _request_with_access_token(token: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/me",
            "headers": [(b"cookie", f"access_token={token}".encode())],
        }
    )


def _request_with_internal_token(token: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/ingest/batch",
            "headers": [(b"x-internal-service-token", token.encode())],
        }
    )


@pytest.mark.asyncio
async def test_require_user_falls_back_to_user_service_token_validation(monkeypatch):
    monkeypatch.setattr(AuthService.AuthService, "is_keycloak_enabled", staticmethod(lambda: True))

    def raise_invalid_keycloak_token(token: str) -> dict:
        raise UnauthorizedError(message="Invalid bearer token")

    user_service_user = {
        "id": "4bde69c3-aec6-42c7-a4e0-5d73bf033594",
        "email": "ada@example.com",
        "username": "ada",
        "role": "member",
    }

    monkeypatch.setattr(
        api_dependencies,
        "_decode_keycloak_token",
        raise_invalid_keycloak_token,
    )
    monkeypatch.setattr(
        AuthService,
        "get_user_service_current_user",
        AsyncMock(return_value=user_service_user),
    )

    user = await require_user(_request_with_access_token("user-service-token"), None)

    assert user.user_id == user_service_user["id"]
    assert user.email == user_service_user["email"]
    assert user.username == user_service_user["username"]
    assert user.roles == ["member"]
    assert user.access_token == "user-service-token"


@pytest.mark.asyncio
async def test_require_user_or_internal_service_token_accepts_internal_header(monkeypatch):
    monkeypatch.setattr(AuthService.settings, "INTERNAL_SERVICE_TOKEN", "internal-token")

    user = await require_user_or_internal_service_token(
        _request_with_internal_token("internal-token"),
        None,
    )

    assert user.user_id == "internal-service"
    assert user.email == "internal@service.local"
    assert user.roles == ["internal"]


def test_decode_keycloak_token_disables_iat_verification(monkeypatch):
    monkeypatch.setattr(AuthService.settings, "KEYCLOAK_ISSUER_URL", "https://issuer")
    monkeypatch.setattr(AuthService.settings, "KEYCLOAK_AUDIENCE", "rag-service")
    monkeypatch.setattr(AuthService.settings, "KEYCLOAK_CLIENT_ID", "agenticai-web")

    class FakeSigningKey:
        key = "signing-key"

    def _get_signing_key(token: str) -> FakeSigningKey:
        assert token == "sample-token"
        return FakeSigningKey()

    def _decode(
        jwt: str,
        key: str,
        algorithms: list[str],
        issuer: str,
        audience: list[str] | None,
        leeway: int,
        options: dict[str, object],
    ) -> dict[str, str]:
        assert key == "signing-key"
        assert issuer == "https://issuer"
        assert options["verify_iss"] is True
        assert options["verify_exp"] is True
        assert options["verify_iat"] is False
        return {"sub": "keycloak-sub"}

    monkeypatch.setattr(
        AuthService.AuthService,
        "get_signing_key",
        staticmethod(_get_signing_key),
    )
    monkeypatch.setattr(AuthService.jwt, "decode", _decode)

    assert AuthService.AuthService.decode_keycloak_token("sample-token") == {
        "sub": "keycloak-sub"
    }
