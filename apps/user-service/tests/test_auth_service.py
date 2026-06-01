from datetime import datetime, timedelta

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
        role="basic",
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
            "role": "basic",
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