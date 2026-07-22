from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from langconnect import auth


def _request(
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
    host: str = "127.0.0.1",
):
    return SimpleNamespace(
        headers=headers or {},
        cookies=cookies or {},
        client=SimpleNamespace(host=host),
    )


def _credentials(token: str):
    return SimpleNamespace(scheme="Bearer", credentials=token)


@pytest.fixture(autouse=True)
def clear_auth_cache(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(auth, "VALID_API_KEYS", set())


def test_verify_api_key_uses_bearer_identity_in_test_mode(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(auth, "IS_TESTING", True)
    monkeypatch.setattr(auth.config, "KEYCLOAK_ENABLED", False)
    assert auth.verify_api_key("user1") == "user1"
    assert auth.verify_api_key("api-key:user2") == "user2"


def test_claim_permissions_supports_permissions_claim_and_client_roles(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(auth.config, "KEYCLOAK_CLIENT_ID", "agenticai-web")

    assert auth._claims_have_permission(
        {"permissions": ["collection:create"]},
        "collection:create",
    )
    assert auth._claims_have_permission(
        {"resource_access": {"agenticai-web": {"roles": ["document:read"]}}},
        "document:read",
    )
    assert auth._claims_have_permission(
        {"realm_access": {"roles": ["*"]}},
        "graph:read",
    )


async def test_resolve_user_requires_credentials_in_test_mode(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(auth, "IS_TESTING", True)
    monkeypatch.setattr(auth.config, "KEYCLOAK_ENABLED", False)
    with pytest.raises(HTTPException) as exc:
        await auth.resolve_user(_request(), None)

    assert exc.value.status_code == 401


async def test_resolve_user_does_not_trust_localhost_without_flag(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(auth, "IS_TESTING", False)
    monkeypatch.setattr(auth, "VALID_API_KEYS", {"expected-key"})

    with pytest.raises(HTTPException) as exc:
        await auth.resolve_user(
            _request(headers={"User-Agent": "python-httpx/0.28.1"}),
            None,
        )

    assert exc.value.status_code == 403


async def test_resolve_user_accepts_internal_service_token(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(auth, "INTERNAL_SERVICE_TOKEN", "internal-token")
    user = await auth.resolve_user(
        _request(headers={"X-Internal-Service-Token": "internal-token"}),
        None,
    )
    assert user is not None
    assert user.identity == "internal-service"


async def test_resolve_user_uses_bearer_identity_in_test_mode(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(auth, "IS_TESTING", True)
    monkeypatch.setattr(auth.config, "KEYCLOAK_ENABLED", False)
    user = await auth.resolve_user(_request(), _credentials("user-123"))
    assert user is not None
    assert user.identity == "user-123"
    assert user.access_token == "user-123"


async def test_resolve_user_uses_access_token_cookie_in_test_mode(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(auth, "IS_TESTING", True)
    monkeypatch.setattr(auth.config, "KEYCLOAK_ENABLED", False)
    user = await auth.resolve_user(
        _request(cookies={"access_token": "cookie-user"}),
        None,
    )
    assert user is not None
    assert user.identity == "cookie-user"
    assert user.access_token == "cookie-user"


async def test_resolve_user_maps_keycloak_token_to_local_user(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(auth.config, "KEYCLOAK_ENABLED", True)
    monkeypatch.setattr(auth.config, "KEYCLOAK_ISSUER_URL", "https://issuer")

    def _decode_token(token: str):
        assert token == "jwt-token"
        return {"sub": "keycloak-sub", "email": "demo@example.com"}

    async def _get_user(token: str):
        assert token == "jwt-token"
        return {"id": "local-user-id", "email": "local@example.com"}

    monkeypatch.setattr(auth, "decode_keycloak_token", _decode_token)
    monkeypatch.setattr(auth, "_get_user_service_user", _get_user)

    user = await auth.resolve_user(_request(), _credentials("jwt-token"))

    assert user is not None
    assert user.identity == "local-user-id"
    assert user.display_name == "local@example.com"
    assert user.access_token == "jwt-token"
