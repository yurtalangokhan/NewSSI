"""Tests for scoped, direct-only organization resource permission synchronization."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import require_auth
from src.api.routes import resource_permissions_route
from src.api.routes.resource_permissions_route import router
from src.controller.resource_permission_controller import ResourcePermissionController
from src.core.exceptions import ForbiddenError, NotFoundError
from src.schema.organizations import (
    ResourcePermissionSyncItem,
    ScopedResourcePermissionSyncRequest,
)
from src.service.resource_permission_service import ResourcePermissionService


@pytest.fixture
def service() -> ResourcePermissionService:
    """Return a resource permission service with isolated collaborators."""
    instance = ResourcePermissionService()
    instance.perm_repo = MagicMock()
    instance.user_organization_service = MagicMock()
    instance.user_organization_service.can_manage_organization = AsyncMock(return_value=True)
    instance.user_organization_service.check_user_organization_permission = AsyncMock(
        return_value=True
    )
    instance.org_repo = MagicMock()
    instance.org_repo.get_by_id = AsyncMock(return_value={"id": uuid.uuid4()})
    return instance


@pytest.mark.asyncio
async def test_sync_updates_grants_and_revokes_only_direct_permissions(
    service: ResourcePermissionService,
) -> None:
    """Synchronizing a member target changes only its direct permission records."""
    actor_id = uuid.uuid4()
    organization_id = uuid.uuid4()
    target_user_id = uuid.uuid4()
    updated_permission_id = uuid.uuid4()
    revoked_permission_id = uuid.uuid4()

    expected = [
        {"id": updated_permission_id, "resource_id": "agent-1"},
        {"id": revoked_permission_id, "resource_id": "agent-3"},
    ]
    service.perm_repo.sync_direct_permissions = AsyncMock(return_value=(expected, []))
    payload = ScopedResourcePermissionSyncRequest(
        permissions=[
            ResourcePermissionSyncItem(
                resource_id="agent-1",
                resource_name="Existing agent",
                permission_level="admin",
            ),
            ResourcePermissionSyncItem(
                resource_id="agent-3",
                resource_name="New agent",
                permission_level="execute",
            ),
        ]
    )

    result = await service.sync_scoped_direct_permissions(
        actor_id=actor_id,
        organization_id=organization_id,
        target_type="user",
        target_id=target_user_id,
        resource_type="agent",
        desired_permissions=[item.model_dump() for item in payload.permissions],
    )

    service.perm_repo.sync_direct_permissions.assert_awaited_once_with(
        target_type="user",
        target_id=target_user_id,
        resource_type="agent",
        desired_permissions=[item.model_dump() for item in payload.permissions],
        granted_by=actor_id,
    )
    assert [permission["resource_id"] for permission in result] == ["agent-1", "agent-3"]


@pytest.mark.asyncio
async def test_sync_audits_grants_updates_and_revokes(
    service: ResourcePermissionService,
) -> None:
    """Every mutation reported by the atomic sync is written to the audit log."""
    actor_id = uuid.uuid4()
    organization_id = uuid.uuid4()
    grant_id = uuid.uuid4()
    update_id = uuid.uuid4()
    revoke_id = uuid.uuid4()
    final_permissions = [
        {"id": grant_id, "resource_id": "agent-new"},
        {"id": update_id, "resource_id": "agent-updated"},
    ]
    changes = [
        {
            "action": "grant",
            "permission": {
                "id": grant_id,
                "organization_id": organization_id,
                "user_id": None,
                "resource_type": "agent",
                "resource_id": "agent-new",
                "resource_name": "New agent",
                "permission_level": "read",
                "is_inherited": False,
                "granted_by": actor_id,
            },
            "old_permission_level": None,
        },
        {
            "action": "update",
            "permission": {
                "id": update_id,
                "organization_id": organization_id,
                "user_id": None,
                "resource_type": "agent",
                "resource_id": "agent-updated",
                "resource_name": "Updated agent",
                "permission_level": "admin",
                "is_inherited": False,
                "granted_by": actor_id,
            },
            "old_permission_level": "read",
        },
        {
            "action": "revoke",
            "permission": {
                "id": revoke_id,
                "organization_id": organization_id,
                "user_id": None,
                "resource_type": "agent",
                "resource_id": "agent-revoked",
                "resource_name": "Revoked agent",
                "permission_level": "execute",
                "is_inherited": False,
                "granted_by": actor_id,
            },
            "old_permission_level": "execute",
        },
    ]
    service.perm_repo.sync_direct_permissions = AsyncMock(return_value=(final_permissions, changes))
    service.audit_repo = MagicMock()
    service.audit_repo.create = AsyncMock(return_value={})

    result = await service.sync_scoped_direct_permissions(
        actor_id=actor_id,
        organization_id=organization_id,
        target_type="organization",
        target_id=organization_id,
        resource_type="agent",
        desired_permissions=[],
    )

    assert result == final_permissions
    assert [call.kwargs["action"] for call in service.audit_repo.create.await_args_list] == [
        "grant",
        "update",
        "revoke",
    ]
    assert service.audit_repo.create.await_args_list[1].kwargs["old_permission_level"] == "read"
    assert service.audit_repo.create.await_args_list[2].kwargs["old_permission_level"] == "execute"


@pytest.mark.asyncio
async def test_sync_surfaces_audit_failure(service: ResourcePermissionService) -> None:
    """A failed audit write is visible to the caller instead of being silently skipped."""
    actor_id = uuid.uuid4()
    organization_id = uuid.uuid4()
    permission = {
        "id": uuid.uuid4(),
        "organization_id": organization_id,
        "user_id": None,
        "resource_type": "agent",
        "resource_id": "agent-1",
        "resource_name": "Agent",
        "permission_level": "read",
        "is_inherited": False,
        "granted_by": actor_id,
    }
    service.perm_repo.sync_direct_permissions = AsyncMock(
        return_value=([permission], [{"action": "grant", "permission": permission}])
    )
    service.audit_repo = MagicMock()
    service.audit_repo.create = AsyncMock(side_effect=RuntimeError("audit unavailable"))

    with pytest.raises(RuntimeError, match="audit unavailable"):
        await service.sync_scoped_direct_permissions(
            actor_id=actor_id,
            organization_id=organization_id,
            target_type="organization",
            target_id=organization_id,
            resource_type="agent",
            desired_permissions=[],
        )


@pytest.mark.asyncio
async def test_sync_rejects_user_target_outside_selected_organization(
    service: ResourcePermissionService,
) -> None:
    """A user target must be an active member of the scoped organization."""
    service.user_organization_service.check_user_organization_permission.return_value = False

    with pytest.raises(ValueError, match="active member"):
        await service.sync_scoped_direct_permissions(
            actor_id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            target_type="user",
            target_id=uuid.uuid4(),
            resource_type="rag_collection",
            desired_permissions=[],
        )

    service.perm_repo.sync_direct_permissions.assert_not_called()


@pytest.mark.asyncio
async def test_scoped_operation_checks_organization_exists_before_superuser_bypass(
    service: ResourcePermissionService,
) -> None:
    service.org_repo.get_by_id.return_value = None

    organization_id = uuid.uuid4()
    with pytest.raises(NotFoundError, match="Organization not found"):
        await service.get_scoped_direct_permissions(
            actor_id=uuid.uuid4(),
            organization_id=organization_id,
            target_type="organization",
            target_id=organization_id,
            resource_type="agent",
        )

    service.user_organization_service.can_manage_organization.assert_not_called()


@pytest.mark.asyncio
async def test_scoped_operation_uses_domain_forbidden_error(
    service: ResourcePermissionService,
) -> None:
    organization_id = uuid.uuid4()
    service.org_repo.get_by_id.return_value = {"id": organization_id}
    service.user_organization_service.can_manage_organization.return_value = False

    with pytest.raises(ForbiddenError):
        await service.get_scoped_direct_permissions(
            actor_id=uuid.uuid4(),
            organization_id=organization_id,
            target_type="organization",
            target_id=organization_id,
            resource_type="agent",
        )


@pytest.mark.asyncio
async def test_scoped_read_rejects_mismatched_organization_target(
    service: ResourcePermissionService,
) -> None:
    """An organization target must exactly match the organization in the URL scope."""
    with pytest.raises(ValueError, match="must match"):
        await service.get_scoped_direct_permissions(
            actor_id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            target_type="organization",
            target_id=uuid.uuid4(),
            resource_type="agent",
        )


def test_scoped_resource_permission_routes_are_registered() -> None:
    """The router exposes canonical scoped read and synchronization paths."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    route_paths = {route.path for route in app.routes}
    path = (
        "/api/v1/permissions/organizations/{org_id}/targets/{target_type}/{target_id}"
        "/resources/{resource_type}"
    )

    assert path in route_paths


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [(ForbiddenError("out of scope"), 403), (NotFoundError("Organization not found"), 404)],
)
def test_scoped_route_translates_domain_errors(
    monkeypatch, error: Exception, expected_status: int
) -> None:
    organization_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    service = MagicMock()
    service.get_scoped_direct_permissions = AsyncMock(side_effect=error)
    ctrl = ResourcePermissionController()
    ctrl.service = service
    monkeypatch.setattr(
        resource_permissions_route, "get_resource_permission_controller", lambda: ctrl
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_auth] = lambda: str(actor_id)

    response = TestClient(app).get(
        f"/permissions/organizations/{organization_id}/targets/organization/"
        f"{organization_id}/resources/agent"
    )

    assert response.status_code == expected_status
    service.get_scoped_direct_permissions.assert_awaited_once_with(
        actor_id=actor_id,
        organization_id=organization_id,
        target_type="organization",
        target_id=organization_id,
        resource_type="agent",
    )


def test_scoped_sync_route_forwards_actor_and_organization_target(monkeypatch) -> None:
    organization_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    service = MagicMock()
    service.sync_scoped_direct_permissions = AsyncMock(return_value=[])
    ctrl = ResourcePermissionController()
    ctrl.service = service
    monkeypatch.setattr(
        resource_permissions_route, "get_resource_permission_controller", lambda: ctrl
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_auth] = lambda: str(actor_id)

    response = TestClient(app).put(
        f"/permissions/organizations/{organization_id}/targets/organization/"
        f"{organization_id}/resources/rag_collection",
        json={"permissions": []},
    )

    assert response.status_code == 200
    service.sync_scoped_direct_permissions.assert_awaited_once_with(
        actor_id=actor_id,
        organization_id=organization_id,
        target_type="organization",
        target_id=organization_id,
        resource_type="rag_collection",
        desired_permissions=[],
    )


@pytest.mark.asyncio
async def test_effective_access_does_not_traverse_parent_organizations(
    service: ResourcePermissionService,
) -> None:
    user_id = uuid.uuid4()
    organization_id = uuid.uuid4()
    service.perm_repo.get_by_user_resource = AsyncMock(return_value=None)
    service.perm_repo.get_by_org_resource = AsyncMock(return_value=None)
    service.user_org_repo = MagicMock()
    service.user_org_repo.get_user_organizations = AsyncMock(
        return_value=[{"organization_id": organization_id, "organization": {"name": "Unit"}}]
    )
    service.org_repo.get_ancestors = AsyncMock(
        side_effect=AssertionError("direct-only access must not query ancestors")
    )

    result = await service.check_resource_access(user_id, "agent", "agent-1")

    assert result["allowed"] is False
    service.org_repo.get_ancestors.assert_not_called()


@pytest.mark.asyncio
async def test_accessible_resource_listing_does_not_emit_inherited_permissions(
    service: ResourcePermissionService,
) -> None:
    user_id = uuid.uuid4()
    organization_id = uuid.uuid4()
    service.perm_repo.get_user_permissions = AsyncMock(return_value=[])
    service.perm_repo.get_organization_permissions = AsyncMock(return_value=[])
    service.user_org_repo = MagicMock()
    service.user_org_repo.get_user_organizations = AsyncMock(
        return_value=[{"organization_id": organization_id}]
    )
    service.org_repo.get_ancestors = AsyncMock(
        side_effect=AssertionError("direct-only listing must not query ancestors")
    )

    result = await service.get_user_accessible_resources(user_id, "agent")

    assert result == []
    service.org_repo.get_ancestors.assert_not_called()
