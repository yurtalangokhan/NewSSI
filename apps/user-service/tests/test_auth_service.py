import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from jose import jwt

from src.config import get_settings
from src.service.auth_service import AuthService


@pytest.mark.asyncio
async def test_validate_token_accepts_current_service_tokens():
    auth_service = AuthService()

    token, _ = auth_service._create_access_token(
        user_id="user-123",
        email="user@example.com",
        role="enduser",
    )

    payload = await auth_service.validate_token(token)

    assert payload is not None
    assert payload["sub"] == "user-123"
    assert payload["aud"] == get_settings().SERVICE_NAME


@pytest.mark.asyncio
async def test_validate_token_accepts_legacy_tokens_without_audience():
    settings = get_settings()
    secret = settings.AUTH_SECRET or "dev-secret-change-me"
    token = jwt.encode(
        {
            "sub": "legacy-user",
            "email": "legacy@example.com",
            "role": "enduser",
            "exp": datetime.utcnow() + timedelta(hours=1),
            "iat": datetime.utcnow(),
            "iss": "user-service",
            "type": "access",
        },
        secret,
        algorithm="HS256",
    )

    payload = await AuthService().validate_token(token)

    assert payload is not None
    assert payload["sub"] == "legacy-user"


@pytest.mark.asyncio
async def test_refresh_access_token_requires_keycloak_session_management():
    auth_service = AuthService()
    auth_service.keycloak = SimpleNamespace(is_enabled=lambda: False)

    with pytest.raises(ValueError, match="handled by Keycloak"):
        await auth_service.refresh_access_token("old-refresh-token")


@pytest.mark.asyncio
async def test_refresh_access_token_uses_keycloak_without_local_session_lookup():
    auth_service = AuthService()
    keycloak_id = "sp-keycloak-id"
    id_token = jwt.encode(
        {
            "sub": keycloak_id,
            "email": "user@example.com",
            "preferred_username": "user",
            "given_name": "Test",
            "family_name": "User",
            "groups": ["engineering"],
        },
        "unused",
        algorithm="HS256",
    )
    auth_service.keycloak = SimpleNamespace(
        is_enabled=lambda: True,
        is_external_keycloak=lambda: False,
        refresh_token_grant=AsyncMock(
            return_value={
                "access_token": "sp-access-token",
                "refresh_token": "sp-refresh-token",
                "id_token": id_token,
                "token_type": "Bearer",
                "expires_in": 300,
            }
        ),
    )
    user = SimpleNamespace(
        id=uuid.uuid4(),
        email="user@example.com",
        username="user",
        first_name="Test",
        last_name="User",
        role="enduser",
        groups=["engineering"],
        is_active=True,
        is_verified=True,
        is_superuser=False,
    )
    auth_service.user_repo.upsert_by_keycloak_id = AsyncMock(return_value=user)

    result = await auth_service.refresh_access_token("sp-refresh-token")

    assert result["access_token"] == "sp-access-token"
    assert result["refresh_token"] == "sp-refresh-token"
    assert result["expires_in"] == 300
    auth_service.keycloak.refresh_token_grant.assert_awaited_once_with("sp-refresh-token")
    auth_service.user_repo.upsert_by_keycloak_id.assert_awaited_once_with(
        keycloak_id,
        email="user@example.com",
        username="user",
        first_name="Test",
        last_name="User",
        groups=["engineering"],
        is_active=True,
        is_verified=True,
        is_external_keycloak_user=False,
    )


@pytest.mark.asyncio
async def test_refresh_access_token_does_not_fallback_to_local_session_when_keycloak_fails():
    auth_service = AuthService()
    auth_service.keycloak = SimpleNamespace(
        is_enabled=lambda: True,
        refresh_token_grant=AsyncMock(side_effect=ValueError("invalid_grant")),
    )

    with pytest.raises(ValueError, match="invalid_grant"):
        await auth_service.refresh_access_token("local-refresh-token")

    auth_service.keycloak.refresh_token_grant.assert_awaited_once_with("local-refresh-token")


@pytest.mark.asyncio
async def test_logout_delegates_session_invalidation_to_keycloak():
    auth_service = AuthService()
    auth_service.keycloak = SimpleNamespace(
        is_enabled=lambda: True,
        backchannel_logout=AsyncMock(return_value=True),
    )

    result = await auth_service.logout("refresh-token")

    assert result == {"message": "Logged out successfully"}
    auth_service.keycloak.backchannel_logout.assert_awaited_once_with(
        refresh_token="refresh-token"
    )
    assert not hasattr(auth_service, "session_repo")


def test_extract_roles_from_claims_supports_realm_and_client_roles():
    claims = {
        "realm_access": {"roles": ["offline_access", "uma_authorization"]},
        "resource_access": {
            "agenticai-web": {"roles": ["admin"]},
            "account": {"roles": ["manage-account"]},
        },
    }

    roles = AuthService._extract_roles_from_claims(claims)

    assert "offline_access" in roles
    assert "admin" in roles
    assert "manage-account" in roles


def test_resolve_role_detects_admin_from_client_roles():
    roles = ["manage-account", "ADMIN", "view-profile"]

    resolved = AuthService._resolve_role(roles)

    assert resolved == "system-admin"


def test_get_auth_type_includes_external_keycloak_metadata():
    auth_service = AuthService()
    auth_service.keycloak = SimpleNamespace(
        is_enabled=lambda: True,
        is_external_keycloak=lambda: True,
        get_external_keycloak_alias=lambda: "company-idp",
    )

    metadata = auth_service.get_auth_type()

    assert metadata["authType"] == "oidc"
    assert metadata["externalKeycloak"] is True
    assert metadata["external_keycloak"] is True
    assert metadata["externalKeycloakAlias"] == "company-idp"


@pytest.mark.asyncio
async def test_basic_login_uses_keycloak_tokens_without_local_password_storage():
    auth_service = AuthService()
    keycloak_id = "sp-keycloak-id"
    id_token = jwt.encode(
        {
            "sub": keycloak_id,
            "email": "newuser@example.com",
            "preferred_username": "newuser",
            "given_name": "New",
            "family_name": "User",
            "realm_access": {"roles": ["enduser"]},
        },
        "unused",
        algorithm="HS256",
    )
    auth_service.keycloak = SimpleNamespace(
        is_enabled=lambda: True,
        is_external_keycloak=lambda: False,
        password_grant=AsyncMock(
            return_value={
                "access_token": "sp-access-token",
                "refresh_token": "sp-refresh-token",
                "id_token": id_token,
                "token_type": "Bearer",
                "expires_in": 300,
            }
        ),
    )
    user = SimpleNamespace(
        id=uuid.uuid4(),
        email="newuser@example.com",
        username="newuser",
        first_name="New",
        last_name="User",
        role="enduser",
        groups=[],
        is_active=True,
        is_verified=True,
        is_superuser=False,
    )
    auth_service.user_repo.upsert_by_keycloak_id = AsyncMock(return_value=user)

    result = await auth_service.basic_login("newuser@example.com", "securepassword123")

    assert result["access_token"] == "sp-access-token"
    assert result["refresh_token"] == "sp-refresh-token"
    auth_service.keycloak.password_grant.assert_awaited_once_with(
        "newuser@example.com",
        "securepassword123",
    )
    auth_service.user_repo.upsert_by_keycloak_id.assert_awaited_once_with(
        keycloak_id,
        email="newuser@example.com",
        username="newuser",
        first_name="New",
        last_name="User",
        role="enduser",
        groups=[],
        is_active=True,
        is_verified=True,
        is_external_keycloak_user=False,
    )


@pytest.mark.asyncio
async def test_register_is_managed_by_keycloak():
    auth_service = AuthService()

    with pytest.raises(ValueError, match="registration is managed by Keycloak"):
        await auth_service.register(
            username="newuser",
            email="newuser@example.com",
            password="securepassword123",
            first_name="New",
            last_name="User",
        )


@pytest.mark.asyncio
async def test_external_keycloak_login_uses_sp_brokered_idp_credentials():
    auth_service = AuthService()
    keycloak_id = "sp-keycloak-id"
    id_token = jwt.encode(
        {
            "sub": keycloak_id,
            "email": "external@example.com",
            "preferred_username": "external",
            "given_name": "External",
            "family_name": "User",
            "groups": ["engineering"],
        },
        "unused",
        algorithm="HS256",
    )
    auth_service.keycloak = SimpleNamespace(
        is_enabled=lambda: True,
        is_external_keycloak=lambda: False,
        external_broker_password_login=AsyncMock(
            return_value={
                "access_token": "sp-access-token",
                "refresh_token": "sp-refresh-token",
                "id_token": id_token,
                "token_type": "Bearer",
                "expires_in": 300,
            }
        ),
    )
    user_id = uuid.uuid4()
    auth_service.user_repo.upsert_by_keycloak_id = AsyncMock(
        return_value=SimpleNamespace(
            id=user_id,
            email="external@example.com",
            username="external",
            first_name="External",
            last_name="User",
            role="enduser",
            groups=["engineering"],
            is_active=True,
            is_verified=True,
            is_superuser=False,
        )
    )

    result = await auth_service.external_keycloak_login("external@example.com", "secret")

    assert result["access_token"] == "sp-access-token"
    assert result["refresh_token"] == "sp-refresh-token"
    assert result["user"]["id"] == str(user_id)
    auth_service.keycloak.external_broker_password_login.assert_awaited_once_with(
        "external@example.com",
        "secret",
    )
    auth_service.user_repo.upsert_by_keycloak_id.assert_awaited_once_with(
        keycloak_id,
        email="external@example.com",
        username="external",
        first_name="External",
        last_name="User",
        role="enduser",
        groups=["engineering"],
        is_active=True,
        is_verified=True,
        is_external_keycloak_user=False,
    )


@pytest.mark.asyncio
async def test_handle_oidc_callback_persists_groups_from_sp_id_token():
    auth_service = AuthService()
    keycloak_id = "sp-keycloak-id"
    id_token = jwt.encode(
        {
            "sub": keycloak_id,
            "email": "external@example.com",
            "preferred_username": "external",
            "given_name": "External",
            "family_name": "User",
            "groups": ["engineering", "arge"],
        },
        "unused",
        algorithm="HS256",
    )
    auth_service.keycloak = SimpleNamespace(
        is_external_keycloak=lambda: False,
        handle_oidc_callback=AsyncMock(
            return_value={
                "access_token": "sp-access-token",
                "refresh_token": "sp-refresh-token",
                "id_token": id_token,
                "token_type": "Bearer",
                "expires_in": 300,
            }
        ),
    )
    auth_service.user_repo.upsert_by_keycloak_id = AsyncMock(
        return_value=SimpleNamespace(
            id=uuid.uuid4(),
            email="external@example.com",
            username="external",
            first_name="External",
            last_name="User",
            role="enduser",
            groups=["engineering", "arge"],
            is_active=True,
            is_verified=True,
            is_superuser=False,
        )
    )

    result = await auth_service.handle_oidc_callback(
        "code",
        "http://localhost:3000/auth/oidc/callback",
    )

    assert result["user"]["groups"] == ["engineering", "arge"]
    auth_service.user_repo.upsert_by_keycloak_id.assert_awaited_once_with(
        keycloak_id,
        email="external@example.com",
        username="external",
        first_name="External",
        last_name="User",
        role="enduser",
        groups=["engineering", "arge"],
        is_active=True,
        is_verified=True,
        is_external_keycloak_user=False,
    )


@pytest.mark.asyncio
async def test_refresh_access_token_rejects_when_keycloak_refresh_fails():
    auth_service = AuthService()
    auth_service.keycloak = SimpleNamespace(
        is_enabled=lambda: True,
        refresh_token_grant=AsyncMock(side_effect=ValueError("invalid_grant")),
    )

    with pytest.raises(ValueError, match="invalid_grant"):
        await auth_service.refresh_access_token("local-refresh-token")

    auth_service.keycloak.refresh_token_grant.assert_awaited_once_with("local-refresh-token")


def test_extract_groups_from_claims_supports_group_and_groups_claims():
    assert AuthService._extract_groups_from_claims({"groups": ["a", "/b"]}) == ["a", "/b"]
    assert AuthService._extract_groups_from_claims({"group": "arge"}) == ["arge"]
    assert AuthService._extract_groups_from_claims({"groups": None}) == []
