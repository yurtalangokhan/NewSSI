from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import pytest
from jose import jwt

from src.config import get_settings
from src.service.auth_service import AuthService


def test_hash_password_generates_bcrypt_hash():
    hashed = AuthService.hash_password("test123")

    assert hashed.startswith("$2")
    assert AuthService.verify_password("test123", hashed)


def test_verify_password_rejects_invalid_hashes():
    assert AuthService.verify_password("test123", "not-a-valid-hash") is False


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

    assert resolved == "admin"


@pytest.mark.asyncio
async def test_basic_login_raises_when_keycloak_auth_fails_in_oidc_mode():
    auth_service = AuthService()
    auth_service.keycloak = SimpleNamespace(is_enabled=lambda: True)
    auth_service.session_repo.create = AsyncMock()
    auth_service.keycloak.password_grant = AsyncMock(
        side_effect=ValueError("Account is not fully set up")
    )

    user = SimpleNamespace(
        id=uuid.uuid4(),
        email="newuser@example.com",
        username="newuser",
        first_name=None,
        last_name=None,
        role="enduser",
        is_active=True,
        is_verified=False,
        is_superuser=False,
        hashed_password=AuthService.hash_password("securepassword123"),
    )
    auth_service.user_repo.get_by_email = AsyncMock(return_value=user)
    auth_service.user_repo.get_by_username = AsyncMock(return_value=None)

    with pytest.raises(ValueError, match="Account is not fully set up"):
        await auth_service.basic_login("newuser@example.com", "securepassword123")

    auth_service.user_repo.get_by_email.assert_not_called()
    auth_service.user_repo.get_by_username.assert_not_called()
    auth_service.keycloak.password_grant.assert_awaited_once()
