from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from api.routes.ChatRoute import _resolve_effective_chat_user_id
from api.routes.UserMemoryRoute import _resolve_memory_user_id
from service.AuthService import get_primary_user_id


def _build_request() -> Request:
    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request({"type": "http", "method": "GET", "headers": []}, receive)


def test_get_primary_user_id_prefers_identity_primary() -> None:
    identity = {"primary_user_id": "internal-user", "known_user_ids": ["internal-user", "kc-sub"]}

    assert get_primary_user_id(identity, "kc-sub") == "internal-user"


def test_resolve_effective_chat_user_id_uses_primary_user_id() -> None:
    identity = {"primary_user_id": "internal-user", "known_user_ids": ["internal-user", "kc-sub"]}

    assert _resolve_effective_chat_user_id(identity, "kc-sub") == "internal-user"


def test_resolve_effective_chat_user_id_raises_without_any_user_id() -> None:
    with pytest.raises(HTTPException):
        _resolve_effective_chat_user_id({}, None)


@pytest.mark.asyncio
async def test_resolve_memory_user_id_uses_primary_user_id(monkeypatch: pytest.MonkeyPatch) -> None:
    auth_service = AsyncMock()
    auth_service.resolve_user_identity = AsyncMock(
        return_value={"primary_user_id": "internal-user", "known_user_ids": ["internal-user", "kc-sub"]}
    )
    monkeypatch.setattr("api.routes.UserMemoryRoute.get_auth_service", lambda: auth_service)

    effective_user_id = await _resolve_memory_user_id(_build_request(), "kc-sub")

    assert effective_user_id == "internal-user"


@pytest.mark.asyncio
async def test_resolve_memory_user_id_falls_back_to_raw_user_id(monkeypatch: pytest.MonkeyPatch) -> None:
    auth_service = AsyncMock()
    auth_service.resolve_user_identity = AsyncMock(return_value={"primary_user_id": None, "known_user_ids": ["kc-sub"]})
    monkeypatch.setattr("api.routes.UserMemoryRoute.get_auth_service", lambda: auth_service)

    effective_user_id = await _resolve_memory_user_id(_build_request(), "kc-sub")

    assert effective_user_id == "kc-sub"