import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.api import dependencies
from src.api.dependencies import require_admin, require_auth, require_auth_or_internal_service_token
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
async def test_get_user_permissions_returns_composite_role_permissions_without_bypass():
    user_id = uuid.uuid4()
    service = UserService()
    service.user_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=SimpleNamespace(role="member"))
    )
    service.permission_resolver = SimpleNamespace(
        resolve_effective_permissions=AsyncMock(return_value=["user:list"])
    )

    assert await service.get_user_permissions(user_id) == {"permissions": ["user:list"]}


@pytest.mark.asyncio
async def test_get_user_permissions_returns_role_permissions():
    user_id = uuid.uuid4()
    service = UserService()
    service.user_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=SimpleNamespace(role="analyst"))
    )
    service.permission_resolver = SimpleNamespace(
        resolve_effective_permissions=AsyncMock(return_value=["user:list"])
    )

    assert await service.get_user_permissions(user_id) == {"permissions": ["user:list"]}


@pytest.mark.asyncio
async def test_user_has_permission_returns_allowed_decision():
    user_id = uuid.uuid4()
    service = UserService()
    service.user_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=SimpleNamespace(role="analyst"))
    )
    service.permission_resolver = SimpleNamespace(
        resolve_effective_permissions=AsyncMock(return_value=["user:list"])
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
async def test_get_user_permissions_preserves_permission_wildcard():
    user_id = uuid.uuid4()
    service = UserService()
    service.user_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=SimpleNamespace(role="system-admin"))
    )
    service.permission_resolver = SimpleNamespace(
        resolve_effective_permissions=AsyncMock(return_value=["*"])
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


@pytest.mark.asyncio
async def test_require_admin_denial_uses_admin_required_translation(monkeypatch):
    user_id = uuid.uuid4()

    class Repo:
        async def get_by_id(self, requested_user_id):
            assert requested_user_id == user_id
            return SimpleNamespace(id=user_id)

    resolver = SimpleNamespace(resolve_effective_permissions=AsyncMock(return_value=[]))
    monkeypatch.setattr(dependencies, "UserRepository", Repo)
    monkeypatch.setattr(
        dependencies,
        "get_permission_resolver_service",
        lambda: resolver,
    )

    with pytest.raises(HTTPException) as exc:
        await require_admin(SimpleNamespace(), str(user_id))

    assert exc.value.status_code == 403
    assert exc.value.detail == "Admin access required"


def test_internal_permissions_endpoint_resolves_target_user(monkeypatch):
    target_id = uuid.uuid4()
    controller = SimpleNamespace(
        authorize_target_user_id=AsyncMock(return_value=target_id),
        get_user_permissions=AsyncMock(return_value={"permissions": ["document:read"]}),
    )
    monkeypatch.setattr(user_route, "get_user_controller", lambda: controller)

    app = FastAPI()
    app.dependency_overrides[require_auth_or_internal_service_token] = lambda: "internal-service"
    app.include_router(user_route.internal_router)

    response = TestClient(app).get(f"/internal/users/{target_id}/permissions")

    assert response.status_code == 200
    assert response.json() == {"permissions": ["document:read"]}
    controller.authorize_target_user_id.assert_awaited_once_with(
        str(target_id),
        "internal-service",
    )
    controller.get_user_permissions.assert_awaited_once_with(target_id)


def test_internal_authorize_endpoint_resolves_target_user(monkeypatch):
    target_id = uuid.uuid4()
    controller = SimpleNamespace(
        authorize_target_user_id=AsyncMock(return_value=target_id),
        authorize_user_permission=AsyncMock(
            return_value={"allowed": True, "permission": "document:read"}
        ),
    )
    monkeypatch.setattr(user_route, "get_user_controller", lambda: controller)

    app = FastAPI()
    app.dependency_overrides[require_auth_or_internal_service_token] = lambda: "internal-service"
    app.include_router(user_route.internal_router)

    response = TestClient(app).post(
        "/internal/users/authorize",
        json={"target_id": str(target_id), "permission": "document:read"},
    )

    assert response.status_code == 200
    assert response.json() == {"allowed": True, "permission": "document:read"}
    controller.authorize_target_user_id.assert_awaited_once_with(
        str(target_id),
        "internal-service",
    )
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
    service.user_role_repo = SimpleNamespace(assign_roles=AsyncMock())
    service.permission_resolver = SimpleNamespace(invalidate_user=AsyncMock())
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
async def test_get_current_user_preserves_db_role_when_keycloak_has_no_valid_role():
    user_id = uuid.uuid4()
    user = _user(id=user_id, role="system-admin", keycloak_id="kc-user-id")
    service = UserService()
    service.user_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=user),
        update=AsyncMock(),
    )
    service.keycloak = SimpleNamespace(is_enabled=lambda: True)
    service._resolve_role_from_keycloak = AsyncMock(return_value=None)

    result = await service.get_current_user(str(user_id))

    assert result["role"] == "system-admin"
    service.user_repo.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_upsert_external_keycloak_user_preserves_existing_composite_role():
    existing_user = _user(role="system-admin")
    service = UserService()
    service._is_external_keycloak_user = AsyncMock(return_value=True)
    service.user_repo = SimpleNamespace(
        get_by_keycloak_id=AsyncMock(return_value=existing_user),
        upsert_by_keycloak_id=AsyncMock(return_value=existing_user),
    )
    service.settings_repo = SimpleNamespace(ensure_defaults=AsyncMock())

    result = await service.upsert_user_from_keycloak(
        keycloak_id="kc-user-id",
        email="admin@example.com",
        username="admin",
    )

    assert result["role"] == "system-admin"
    service.user_repo.upsert_by_keycloak_id.assert_awaited_once()
    assert "role" not in service.user_repo.upsert_by_keycloak_id.await_args.kwargs


@pytest.mark.asyncio
async def test_upsert_new_external_keycloak_user_gets_default_composite_role():
    created_user = _user(role="enduser")
    service = UserService()
    service._is_external_keycloak_user = AsyncMock(return_value=True)
    service.user_repo = SimpleNamespace(
        get_by_keycloak_id=AsyncMock(return_value=None),
        upsert_by_keycloak_id=AsyncMock(return_value=created_user),
    )
    service.settings_repo = SimpleNamespace(ensure_defaults=AsyncMock())

    result = await service.upsert_user_from_keycloak(
        keycloak_id="new-kc-user-id",
        email="new-user@example.com",
        username="new-user",
    )

    assert result["role"] == "enduser"
    service.user_repo.upsert_by_keycloak_id.assert_awaited_once()
    assert service.user_repo.upsert_by_keycloak_id.await_args.kwargs["role"] == "enduser"


@pytest.mark.asyncio
async def test_resolve_role_from_roles_returns_none_for_only_legacy_keycloak_roles():
    service = UserService()
    service.role_repo = SimpleNamespace(
        get_all=AsyncMock(
            return_value=[
                SimpleNamespace(name="system-admin"),
                SimpleNamespace(name="enduser"),
            ]
        )
    )

    resolved = await service._resolve_role_from_roles([{"name": "admin"}])

    assert resolved is None


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
