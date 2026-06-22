from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from service import AuthService
from service.AuthService import require_user


def _request_with_access_token(token: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/me",
            "headers": [(b"cookie", f"access_token={token}".encode())],
        }
    )


@pytest.mark.asyncio
async def test_require_user_falls_back_to_user_service_token_validation(monkeypatch):
    monkeypatch.setattr(AuthService.AuthService, "is_keycloak_enabled", staticmethod(lambda: True))

    def raise_invalid_keycloak_token(token: str) -> dict:
        raise HTTPException(status_code=401, detail="Invalid bearer token")

    user_service_user = {
        "id": "4bde69c3-aec6-42c7-a4e0-5d73bf033594",
        "email": "ada@example.com",
        "username": "ada",
        "role": "admin",
        "is_superuser": True,
    }

    monkeypatch.setattr(
        AuthService,
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
    assert "admin" in user.roles
    assert user.access_token == "user-service-token"
