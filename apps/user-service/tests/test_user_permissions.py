import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import require_auth, require_auth_or_internal_service_token
from src.api.routes import user_route
from src.service.user_service import UserService


@pytest.mark.asyncio
async def test_get_user_permissions_returns_wildcard_for_superuser():
    user_id = uuid.uuid4()
    service = UserService()
    service.user_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=SimpleNamespace(is_superuser=True, role="enduser"))
    )

    assert await service.get_user_permissions(user_id) == {"permissions": ["*"]}


@pytest.mark.asyncio
async def test_get_user_permissions_returns_role_permissions():
    user_id = uuid.uuid4()
    service = UserService()
    service.user_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=SimpleNamespace(is_superuser=False, role="analyst"))
    )
    service.role_repo = SimpleNamespace(
        get_by_name=AsyncMock(return_value=SimpleNamespace(permissions=["user:list"]))
    )

    assert await service.get_user_permissions(user_id) == {"permissions": ["user:list"]}


@pytest.mark.asyncio
async def test_get_user_permissions_preserves_role_wildcard():
    user_id = uuid.uuid4()
    service = UserService()
    service.user_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=SimpleNamespace(is_superuser=False, role="system-admin"))
    )
    service.role_repo = SimpleNamespace(
        get_by_name=AsyncMock(return_value=SimpleNamespace(permissions=["*"]))
    )

    assert await service.get_user_permissions(user_id) == {"permissions": ["*"]}


def test_me_permissions_endpoint_returns_current_user_permissions(monkeypatch):
    user_id = uuid.uuid4()
    controller = SimpleNamespace(
        get_user_permissions=AsyncMock(return_value={"permissions": ["role:list"]})
    )
    monkeypatch.setattr(user_route, "get_user_controller", lambda: controller)

    app = FastAPI()
    app.dependency_overrides[require_auth] = lambda: str(user_id)
    app.include_router(user_route.router)

    response = TestClient(app).get("/users/me/permissions")

    assert response.status_code == 200
    assert response.json() == {"permissions": ["role:list"]}
    controller.get_user_permissions.assert_awaited_once_with(user_id)


def test_internal_permissions_endpoint_resolves_target_user(monkeypatch):
    target_id = uuid.uuid4()
    controller = SimpleNamespace(
        get_user_permissions=AsyncMock(return_value={"permissions": ["document:read"]})
    )
    monkeypatch.setattr(user_route, "get_user_controller", lambda: controller)
    monkeypatch.setattr(
        user_route,
        "_authorize_target_user_id",
        AsyncMock(return_value=target_id),
    )

    app = FastAPI()
    app.dependency_overrides[require_auth_or_internal_service_token] = lambda: "internal-service"
    app.include_router(user_route.router)

    response = TestClient(app).get(f"/users/internal/{target_id}/permissions")

    assert response.status_code == 200
    assert response.json() == {"permissions": ["document:read"]}
    controller.get_user_permissions.assert_awaited_once_with(target_id)
