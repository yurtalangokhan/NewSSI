"""Focused tests for organization management scope."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import require_auth
from src.api.routes import user_organizations_route
from src.core.database.models import OrganizationModel
from src.core.exceptions import ConflictError, ForbiddenError
from src.service.organization_service import OrganizationService
from src.service.user_organization_service import UserOrganizationService


@pytest.fixture
def service() -> UserOrganizationService:
    """Provide the service with isolated repository dependencies."""
    instance = UserOrganizationService()
    instance.repo = MagicMock()
    instance.user_repo = MagicMock()
    instance.org_repo = MagicMock()
    instance.role_repo = MagicMock()
    return instance


async def test_superuser_can_manage_any_organization(service: UserOrganizationService) -> None:
    """An enterprise superuser bypasses unit-manager scope checks."""
    actor_id = uuid.uuid4()
    org_id = uuid.uuid4()
    service.user_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(is_superuser=True))

    assert await service.can_manage_organization(actor_id, org_id) is True


async def test_admin_role_can_manage_any_organization(service: UserOrganizationService) -> None:
    """Database roles marked as admin bypass unit-manager scope checks."""
    actor_id = uuid.uuid4()
    org_id = uuid.uuid4()
    service.user_repo.get_by_id = AsyncMock(
        return_value=SimpleNamespace(is_superuser=False, role="enterprise-admin")
    )
    service.role_repo.get_by_name = AsyncMock(return_value=SimpleNamespace(is_admin=True))

    assert await service.can_manage_organization(actor_id, org_id) is True
    service.role_repo.get_by_name.assert_awaited_once_with("enterprise-admin")
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
    service.repo.delete.assert_not_called()


async def test_organization_service_rejects_a_second_root_organization() -> None:
    """The enterprise hierarchy has a single root organization."""
    service = OrganizationService()
    service.repo = MagicMock()
    service.repo.get_by_code = AsyncMock(return_value=None)
    service.repo.list_all = AsyncMock(return_value=([{"id": uuid.uuid4()}], 1))

    with pytest.raises(ValueError, match="root organization already exists"):
        await service.create_organization(name="Second root", code="second-root")

    service.repo.create.assert_not_called()


async def test_organization_service_rejects_moving_a_child_to_second_root() -> None:
    service = OrganizationService()
    service.repo = MagicMock()
    org_id = uuid.uuid4()
    service.repo.get_by_id = AsyncMock(return_value={"id": org_id, "parent_id": uuid.uuid4()})

    with pytest.raises(ConflictError, match="root organization already exists"):
        await service.move_organization(org_id, None)

    service.repo.move_organization.assert_not_called()


def test_organization_model_declares_database_single_root_invariant() -> None:
    indexes = {index.name: index for index in OrganizationModel.__table__.indexes}

    assert indexes["uq_organizations_single_root"].unique is True


def test_membership_route_forwards_actor_and_translates_scope_denial(monkeypatch) -> None:
    """Membership writes use the authenticated actor for scoped authorization."""
    actor_id = uuid.uuid4()
    target_user_id = uuid.uuid4()
    organization_id = uuid.uuid4()
    service = MagicMock()
    service.assign_user_to_organization = AsyncMock(side_effect=ForbiddenError("out of scope"))
    monkeypatch.setattr(user_organizations_route, "get_user_organization_service", lambda: service)

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
