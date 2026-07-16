import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import require_auth, require_auth_or_internal_service_token
from src.api.routes import user_route
from src.service.user_service import UserService


def _user(**overrides):
    defaults = {
        "id": uuid.uuid4(),
        "email": "user@example.com",
        "username": "user",
        "first_name": "Test",
        "last_name": "User",
        "is_active": True,
        "is_verified": True,
        "is_superuser": False,
        "role": "enduser",
        "invited": False,
        "password_configured": False,
        "is_external_keycloak_user": False,
        "groups": [],
        "team_name": None,
        "keycloak_id": "kc-user-id",
        "created_at": None,
        "updated_at": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


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
async def test_user_has_permission_returns_allowed_decision():
    user_id = uuid.uuid4()
    service = UserService()
    service.user_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=SimpleNamespace(is_superuser=False, role="analyst"))
    )
    service.role_repo = SimpleNamespace(
        get_by_name=AsyncMock(return_value=SimpleNamespace(permissions=["user:list"]))
    )

    assert await service.user_has_permission(user_id, "user:list") == {
        "allowed": True,
        "permission": "user:list",
    }
    assert await service.user_has_permission(user_id, "user:delete") == {
        "allowed": False,
        "permission": "user:delete",
    }


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


def test_internal_authorize_endpoint_resolves_target_user(monkeypatch):
    target_id = uuid.uuid4()
    controller = SimpleNamespace(
        authorize_user_permission=AsyncMock(
            return_value={"allowed": True, "permission": "document:read"}
        )
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

    response = TestClient(app).post(
        "/users/internal/authorize",
        json={"target_id": str(target_id), "permission": "document:read"},
    )

    assert response.status_code == 200
    assert response.json() == {"allowed": True, "permission": "document:read"}
    controller.authorize_user_permission.assert_awaited_once_with(
        target_id,
        "document:read",
    )


@pytest.mark.asyncio
async def test_set_user_role_invalidates_active_keycloak_sessions():
    user_id = uuid.uuid4()
    updated_user = _user(id=user_id, role="system-admin")
    service = UserService()
    service.role_repo = SimpleNamespace(exists=AsyncMock(return_value=True))
    service.user_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=_user(id=user_id, role="enduser")),
        update=AsyncMock(return_value=updated_user),
    )
    service.keycloak = SimpleNamespace(
        is_enabled=lambda: True,
        set_realm_role=AsyncMock(return_value=True),
        logout_user_sessions=AsyncMock(return_value=True),
    )
    service._resolve_role_from_keycloak = AsyncMock(return_value="system-admin")

    result = await service.set_user_role(user_id, "system-admin")

    assert result["role"] == "system-admin"
    service.keycloak.set_realm_role.assert_awaited_once_with("kc-user-id", "system-admin")
    service.keycloak.logout_user_sessions.assert_awaited_once_with("kc-user-id")


@pytest.mark.asyncio
async def test_deactivating_user_invalidates_active_keycloak_sessions():
    user_id = uuid.uuid4()
    service = UserService()
    service.user_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=_user(id=user_id, is_active=True)),
        update=AsyncMock(return_value=_user(id=user_id, is_active=False)),
    )
    service.keycloak = SimpleNamespace(
        is_enabled=lambda: True,
        update_user=AsyncMock(return_value=True),
        logout_user_sessions=AsyncMock(return_value=True),
    )

    result = await service.set_user_active(user_id, False)

    assert result["is_active"] is False
    service.keycloak.logout_user_sessions.assert_awaited_once_with("kc-user-id")
