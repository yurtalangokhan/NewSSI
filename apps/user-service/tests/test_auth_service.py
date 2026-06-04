from datetime import datetime, timedelta

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
