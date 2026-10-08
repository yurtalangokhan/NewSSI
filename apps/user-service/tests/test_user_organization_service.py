"""Focused tests for organization management scope."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from tests.error_support import raises_localized
from src.api.dependencies import require_auth
from src.api.routes import organizations_route, user_organizations_route
from src.controller.user_organization_controller import UserOrganizationController
from src.core.exceptions import BadRequestError, ConflictError, ForbiddenError
from src.repository.user_organization_repository import UserOrganizationRepository
from src.service.organization_service import OrganizationService
from src.service.user_organization_service import UserOrganizationService
from tests.test_keycloak_organizations import CHILD, ROOT, USER, Admin


@pytest.fixture
def service() -> UserOrganizationService:
    """Provide the service with isolated repository dependencies."""
    instance = UserOrganizationService()
    instance.repo = MagicMock()
    instance.user_repo = MagicMock()
    instance.org_repo = MagicMock()
    instance.role_repo = MagicMock()
    instance.user_service = SimpleNamespace(
        set_user_role=AsyncMock(return_value={"role": "builder"})
    )
    instance.user_role_repo = SimpleNamespace(
        get_primary_roles=AsyncMock(return_value={}), list_user_roles=AsyncMock(return_value=[])
    )
    instance.permission_resolver = SimpleNamespace(
        resolve_effective_access=AsyncMock(
            return_value=(["org:read", "org:update", "org:manage-users"], False)
        )
    )
    return instance


async def test_admin_role_can_manage_any_organization(service: UserOrganizationService) -> None:
    """Database roles marked as admin bypass unit-manager scope checks."""
    actor_id = uuid.uuid4()
    org_id = uuid.uuid4()
    service.user_repo.get_by_id = AsyncMock(
        return_value=SimpleNamespace(is_superuser=False, role="enterprise-admin")
    )
    service.permission_resolver.resolve_effective_access.return_value = (["org:read"], True)

    assert await service.can_manage_organization(actor_id, org_id) is True
    service.permission_resolver.resolve_effective_access.assert_awaited_once_with(actor_id)
    service.org_repo.get_by_id.assert_not_called()


async def test_active_unit_manager_can_manage_own_organization_and_descendants(
    service: UserOrganizationService,
) -> None:
    """A manager's unit is the root of the actor's manageable subtree."""
    actor_id = uuid.uuid4()
    managed_org_id = uuid.uuid4()
    descendant_org_id = uuid.uuid4()
    service.user_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(is_superuser=False))
    service.repo.get_active_unit_manager_organizations = AsyncMock(
        return_value=[{"organization_id": managed_org_id}]
    )
    service.org_repo.get_by_id = AsyncMock(
        return_value={"id": descendant_org_id, "path": f"/{managed_org_id}/"}
    )

    assert await service.can_manage_organization(actor_id, managed_org_id) is True
    assert await service.can_manage_organization(actor_id, descendant_org_id) is True


@pytest.mark.parametrize("target_path", ["/", None])
async def test_unit_manager_cannot_manage_ancestor_or_unrelated_organization(
    service: UserOrganizationService, target_path: str | None
) -> None:
    """Manager scope excludes ancestors and sibling branches."""
    actor_id = uuid.uuid4()
    managed_org_id = uuid.uuid4()
    target_org_id = uuid.uuid4()
    service.user_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(is_superuser=False))
    service.repo.get_active_unit_manager_organizations = AsyncMock(
        return_value=[{"organization_id": managed_org_id}]
    )
    service.org_repo.get_by_id = AsyncMock(
        return_value={"id": target_org_id, "path": target_path or f"/{uuid.uuid4()}/"}
    )

    assert await service.can_manage_organization(actor_id, target_org_id) is False


async def test_inactive_unit_manager_cannot_manage_organization(
    service: UserOrganizationService,
) -> None:
    """Only active unit-manager memberships grant management scope."""
    actor_id = uuid.uuid4()
    org_id = uuid.uuid4()
    service.user_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(is_superuser=False))
    service.repo.get_active_unit_manager_organizations = AsyncMock(return_value=[])
    service.org_repo.get_by_id = AsyncMock(return_value={"id": org_id, "path": "/"})

    assert await service.can_manage_organization(actor_id, org_id) is False


async def test_membership_mutations_reject_actor_outside_managed_subtree(
    service: UserOrganizationService,
) -> None:
    """All membership and role writes are guarded by the same actor scope."""
    actor_id = uuid.uuid4()
    target_user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    service.can_manage_organization = AsyncMock(return_value=False)
    service.user_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(is_superuser=False))
    service.org_repo.get_by_id = AsyncMock(return_value={"id": org_id})
    service.repo.get_by_user_and_org = AsyncMock(
        return_value={"id": uuid.uuid4(), "is_active": True}
    )

    with pytest.raises(ForbiddenError):
        await service.assign_user_to_organization(
            target_user_id, org_id, role_in_org="unit_manager", assigned_by=actor_id
        )
    with pytest.raises(ForbiddenError):
        await service.update_user_organization_role(
            target_user_id, org_id, "unit_manager", actor_id=actor_id
        )
    with pytest.raises(ForbiddenError):
        await service.remove_user_from_organization(target_user_id, org_id, actor_id=actor_id)

    service.repo.create.assert_not_called()
    service.repo.update.assert_not_called()
    service.repo.delete_and_cleanup_orphan_permissions.assert_not_called()


async def test_delegated_manager_cannot_assign_admin_role(service):
    service.can_manage_organization = AsyncMock(return_value=True)
    service.user_repo.get_by_id = AsyncMock(return_value=SimpleNamespace())
    service.org_repo.get_by_id = AsyncMock(return_value={"id": uuid.uuid4()})
    service.repo.get_by_user_and_org = AsyncMock(return_value=None)
    service.role_repo.get_by_name = AsyncMock(return_value=SimpleNamespace(name="system-admin"))
    service.repo.create = AsyncMock(return_value={})
    with pytest.raises(ForbiddenError):
        await service.assign_user_to_organization(
            uuid.uuid4(), uuid.uuid4(), role_in_org="system-admin", assigned_by=uuid.uuid4()
        )
    service.repo.create.assert_not_awaited()


@pytest.mark.parametrize(
    ("remaining_memberships", "deleted_permissions"),
    [(1, 0), (0, 3)],
)
async def test_membership_removal_cleans_only_orphaned_user_permissions(
    remaining_memberships: int, deleted_permissions: int
) -> None:
    """The repository preserves grants until the final active membership is removed."""
    admin = Admin()
    if remaining_memberships:
        admin.members[str(USER)].add(str(ROOT))
    repository = UserOrganizationRepository(admin)
    cleanup = AsyncMock(return_value=deleted_permissions)

    async def project(mutation):
        return await mutation()

    with (
        patch(
            "src.repository.resource_permission_repository.ResourcePermissionRepository.delete_user_permissions",
            cleanup,
        ),
        patch(
            "src.repository.keycloak_resource_authorization.project_resource_permission_mutation",
            AsyncMock(side_effect=project),
        ) as projection,
    ):
        result = await repository.delete_and_cleanup_orphan_permissions(USER, CHILD)
    assert result == (True, deleted_permissions)
    assert cleanup.await_count == (0 if remaining_memberships else 1)
    assert projection.await_count == (0 if remaining_memberships else 1)
    assert str(CHILD) not in admin.members[str(USER)]


async def test_assignment_accepts_authoritative_composite_role(
    service: UserOrganizationService,
) -> None:
    """Organization membership accepts a role exposed by the shared role catalog."""
    actor_id = uuid.uuid4()
    target_user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    service.can_manage_organization = AsyncMock(return_value=True)
    service.user_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(id=target_user_id))
    service.org_repo.get_by_id = AsyncMock(return_value={"id": org_id})
    service.repo.get_by_user_and_org = AsyncMock(return_value=None)
    service.role_repo.get_by_name = AsyncMock(return_value=SimpleNamespace(name="builder"))
    service.repo.create = AsyncMock(return_value={"role_in_org": "builder"})
    service.permission_resolver.resolve_effective_access.return_value = (["*"], True)

    result = await service.assign_user_to_organization(
        target_user_id,
        org_id,
        role_in_org="builder",
        assigned_by=actor_id,
    )

    assert result["role_in_org"] == "builder"
    service.role_repo.get_by_name.assert_awaited_once_with("builder")


@pytest.mark.parametrize("role_name", ["member", "viewer", "invented-role"])
async def test_role_update_rejects_role_missing_from_catalog(
    service: UserOrganizationService, role_name: str
) -> None:
    """Legacy and arbitrary client-supplied role names are not persisted."""
    actor_id = uuid.uuid4()
    target_user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    service.can_manage_organization = AsyncMock(return_value=True)
    service.repo.get_by_user_and_org = AsyncMock(
        return_value={"id": uuid.uuid4(), "is_active": True}
    )
    service.role_repo.get_by_name = AsyncMock(return_value=None)

    with raises_localized(BadRequestError, f"Unknown organization role '{role_name}'"):
        await service.update_user_organization_role(
            target_user_id,
            org_id,
            role_name,
            actor_id=actor_id,
        )

    service.repo.update.assert_not_called()


async def test_unit_manager_resolves_authoritative_catalog_role(
    service: UserOrganizationService,
) -> None:
    """The legacy UI alias resolves to the platform role's canonical name."""
    service.role_repo.get_by_name = AsyncMock(return_value=SimpleNamespace(name="Unit Manager"))
    assert await service._require_valid_organization_role("unit_manager") == "Unit Manager"
    service.role_repo.get_by_name.assert_awaited_once_with("Unit Manager")


async def test_repository_lists_all_active_direct_memberships() -> None:
    """Bulk membership reads filter inactive rows and load user identities."""
    repository = UserOrganizationRepository(Admin())
    memberships = await repository.get_all_active_organization_users()
    assert len(memberships) == 1
    assert memberships[0]["organization_id"] == CHILD
    assert memberships[0]["user"]["username"] == "alice"
    await repository.update(memberships[0]["id"], is_active=False)
    assert await repository.get_all_active_organization_users() == []


async def test_service_groups_active_members_by_organization(
    service: UserOrganizationService,
) -> None:
    """The bulk service response groups each direct membership under its unit."""
    first_org_id = uuid.uuid4()
    second_org_id = uuid.uuid4()
    service.repo.get_all_active_organization_users = AsyncMock(
        return_value=[
            {"id": uuid.uuid4(), "user_id": uuid.uuid4(), "organization_id": first_org_id},
            {"id": uuid.uuid4(), "user_id": uuid.uuid4(), "organization_id": second_org_id},
            {"id": uuid.uuid4(), "user_id": uuid.uuid4(), "organization_id": first_org_id},
        ]
    )

    result = await service.get_all_active_organization_users()

    assert list(result) == [str(first_org_id), str(second_org_id)]
    assert len(result[str(first_org_id)]) == 2
    assert len(result[str(second_org_id)]) == 1


async def test_bulk_membership_route_returns_grouped_response(monkeypatch) -> None:
    """The protected bulk route exposes grouped active direct memberships."""
    organization_id = uuid.uuid4()
    user_id = uuid.uuid4()
    grouped = {
        str(organization_id): [
            {
                "id": uuid.uuid4(),
                "user_id": user_id,
                "organization_id": organization_id,
                "role_in_org": "member",
                "is_active": True,
                "user": {"id": user_id, "email": "member@example.com"},
            }
        ]
    }
    controller = MagicMock()
    controller.get_active_members_by_organization = AsyncMock(
        return_value={"members_by_organization": grouped, "count": 1}
    )
    monkeypatch.setattr(
        organizations_route, "get_organization_members_controller", lambda: controller
    )

    response = await organizations_route.get_all_organization_members(
        request=Request({"type": "http", "headers": [], "query_string": b""}),
        response=Response(),
        user_id=str(uuid.uuid4()),
    )

    assert response.data.count == 1
    assert str(organization_id) in response.data.members_by_organization


def test_bulk_membership_route_precedes_dynamic_organization_detail() -> None:
    """The static membership path must not be parsed as an organization UUID."""
    paths = [route.path for route in organizations_route.router.routes]

    assert paths.index("/organizations/members") < paths.index("/organizations/{org_id}")


async def test_organization_service_rejects_a_second_root_organization() -> None:
    """The enterprise hierarchy has a single root organization."""
    service = OrganizationService()
    service.repo = MagicMock()
    service.repo.get_by_code = AsyncMock(return_value=None)
    service.repo.list_all = AsyncMock(return_value=([{"id": uuid.uuid4()}], 1))

    with raises_localized(ConflictError, "root organization already exists"):
        await service.create_organization(name="Second root", code="second-root")

    service.repo.create.assert_not_called()


async def test_organization_service_rejects_moving_a_child_to_second_root() -> None:
    service = OrganizationService()
    service.repo = MagicMock()
    org_id = uuid.uuid4()
    service.repo.get_by_id = AsyncMock(return_value={"id": org_id, "parent_id": uuid.uuid4()})

    with raises_localized(ConflictError, "root organization already exists"):
        await service.move_organization(org_id, None)

    service.repo.move_organization.assert_not_called()


async def test_organization_adapter_preserves_single_root_invariant() -> None:
    from src.repository.organization_repository import OrganizationRepository

    with raises_localized(ConflictError, "root organization already exists"):
        await OrganizationRepository(Admin()).create("Second", "SECOND")


def test_membership_route_forwards_actor_and_translates_scope_denial(monkeypatch) -> None:
    """Membership writes use the authenticated actor for scoped authorization."""
    actor_id = uuid.uuid4()
    target_user_id = uuid.uuid4()
    organization_id = uuid.uuid4()
    service = MagicMock()
    service.assign_user_to_organization = AsyncMock(
        side_effect=ForbiddenError(message="out of scope")
    )
    ctrl = UserOrganizationController()
    ctrl.service = service
    monkeypatch.setattr(user_organizations_route, "get_user_organization_controller", lambda: ctrl)

    app = FastAPI()
    app.include_router(user_organizations_route.router)
    app.dependency_overrides[require_auth] = lambda: str(actor_id)

    response = TestClient(app).post(
        f"/organizations/{organization_id}/users",
        json={"user_id": str(target_user_id), "role_in_org": "unit_manager"},
    )

    assert response.status_code == 403
    service.assign_user_to_organization.assert_awaited_once_with(
        user_id=target_user_id,
        organization_id=organization_id,
        role_in_org="unit_manager",
        is_primary=False,
        assigned_by=actor_id,
    )


def test_membership_route_accepts_bounded_catalog_role_name(monkeypatch) -> None:
    """Request validation permits dynamic role names for service-level validation."""
    actor_id = uuid.uuid4()
    target_user_id = uuid.uuid4()
    organization_id = uuid.uuid4()
    service = MagicMock()
    service.assign_user_to_organization = AsyncMock(
        return_value={"role_in_org": "enterprise-admin"}
    )
    ctrl = UserOrganizationController()
    ctrl.service = service
    monkeypatch.setattr(user_organizations_route, "get_user_organization_controller", lambda: ctrl)

    app = FastAPI()
    app.include_router(user_organizations_route.router)
    app.dependency_overrides[require_auth] = lambda: str(actor_id)

    response = TestClient(app).post(
        f"/organizations/{organization_id}/users",
        json={"user_id": str(target_user_id), "role_in_org": "enterprise-admin"},
    )

    assert response.status_code == 200
    service.assign_user_to_organization.assert_awaited_once_with(
        user_id=target_user_id,
        organization_id=organization_id,
        role_in_org="enterprise-admin",
        is_primary=False,
        assigned_by=actor_id,
    )
