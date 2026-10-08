"""Candidate searches and writes share the actor's organization boundary."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import user_organizations_route
from src.core.exceptions import ForbiddenError
from src.service.organization_scope_service import OrganizationScope
from src.service.user_organization_service import UserOrganizationService
from tests.route_support import override_route_dependencies


@pytest.fixture
def service():
    instance = UserOrganizationService()
    root = uuid.uuid4()
    instance.can_manage_organization = AsyncMock(return_value=True)
    instance.user_service = SimpleNamespace(
        set_user_role=AsyncMock(return_value={"role": "enduser"})
    )
    instance.user_role_repo = SimpleNamespace(list_user_roles=AsyncMock(return_value=[]))
    instance.permission_resolver = SimpleNamespace(
        resolve_effective_access=AsyncMock(return_value=(["org:manage-users"], False))
    )
    instance.scope_service = SimpleNamespace(
        resolve=AsyncMock(return_value=OrganizationScope(False, [{"id": root}]))
    )
    instance.org_repo = SimpleNamespace(get_by_id=AsyncMock(return_value={"id": root}))
    instance.user_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=SimpleNamespace()),
        list_assignable=AsyncMock(return_value=([{"id": uuid.uuid4()}], 45)),
    )
    instance.repo = SimpleNamespace(
        get_by_user_and_org=AsyncMock(return_value=None),
        create=AsyncMock(return_value={}),
        update=AsyncMock(return_value={"is_active": True}),
        update_by_user_and_org=AsyncMock(return_value={"is_active": True}),
    )
    instance.role_repo = SimpleNamespace(
        get_by_name=AsyncMock(return_value=SimpleNamespace(name="end-user"))
    )
    return instance


@pytest.mark.parametrize("global_access", [True, False])
async def test_search_passes_full_actor_scope_and_query(service, global_access):
    scope = service.scope_service.resolve.return_value
    service.scope_service.resolve.return_value = OrganizationScope(global_access, scope.roots)
    destination = scope.root_ids[0]
    result = await service.get_assignable_users(destination, uuid.uuid4(), " late user ", 20)
    assert result["total"] == 45
    service.user_repo.list_assignable.assert_awaited_once_with(
        destination,
        root_ids=None if global_access else scope.root_ids,
        query="late user",
        limit=20,
    )


async def test_search_denies_unrelated_destination(service):
    service.org_repo.get_by_id.return_value = {"id": uuid.uuid4()}
    with pytest.raises(ForbiddenError):
        await service.get_assignable_users(uuid.uuid4(), uuid.uuid4())
    service.user_repo.list_assignable.assert_not_awaited()


async def test_assignment_rejects_forged_external_candidate(service):
    service.user_repo.list_assignable.return_value = ([], 0)
    with pytest.raises(ForbiddenError):
        await service.assign_user_to_organization(
            uuid.uuid4(), uuid.uuid4(), "end-user", assigned_by=uuid.uuid4()
        )
    service.repo.create.assert_not_awaited()


@pytest.mark.parametrize("role", ["unit_manager", "Unit Manager", "builder", "System Admin"])
async def test_delegated_manager_cannot_assign_other_roles(service, role):
    service.role_repo.get_by_name.return_value = SimpleNamespace(name=role)
    with pytest.raises(ForbiddenError):
        await service.assign_user_to_organization(
            uuid.uuid4(), uuid.uuid4(), role, assigned_by=uuid.uuid4()
        )
    service.repo.create.assert_not_awaited()


@pytest.mark.parametrize("role", ["End User", "end_user", "end-user", "enduser"])
@pytest.mark.parametrize("catalog_name", ["end-user", "enduser"])
async def test_end_user_aliases_persist_catalog_name(service, role, catalog_name):
    service.role_repo.get_by_name.return_value = SimpleNamespace(name=catalog_name)
    await service.assign_user_to_organization(
        uuid.uuid4(), uuid.uuid4(), role, assigned_by=uuid.uuid4()
    )
    assert service.user_service.set_user_role.await_args.args[1] == catalog_name
    assert "role_in_org" not in service.repo.create.await_args.kwargs


@pytest.mark.parametrize("role", ["system-admin", "Enterprise Admin", "enterprise_admin"])
async def test_global_admin_cannot_assign_global_roles_to_membership(service, role):
    service.permission_resolver.resolve_effective_access.return_value = (["*"], True)
    with pytest.raises(ForbiddenError):
        await service.assign_user_to_organization(
            uuid.uuid4(), uuid.uuid4(), role, assigned_by=uuid.uuid4()
        )


async def test_global_manager_alias_is_canonical(service):
    service.role_repo.get_by_name.return_value = SimpleNamespace(name="Unit Manager")
    service.permission_resolver.resolve_effective_access.return_value = (["*"], True)
    await service.assign_user_to_organization(
        uuid.uuid4(), uuid.uuid4(), "Unit Manager", assigned_by=uuid.uuid4()
    )
    assert service.user_service.set_user_role.await_args.args[1] == "Unit Manager"
    assert "role_in_org" not in service.repo.create.await_args.kwargs


async def test_inactive_destination_membership_is_reactivated(service):
    membership_id = uuid.uuid4()
    user_id, organization_id = uuid.uuid4(), uuid.uuid4()
    service.repo.get_by_user_and_org.return_value = {"id": membership_id, "is_active": False}
    await service.assign_user_to_organization(
        user_id, organization_id, "end-user", assigned_by=uuid.uuid4()
    )
    assert service.repo.update_by_user_and_org.await_args.args == (user_id, organization_id)
    assert service.repo.update_by_user_and_org.await_args.kwargs["is_active"] is True
    service.repo.update.assert_not_awaited()
    service.repo.create.assert_not_awaited()


async def test_role_update_rejects_delegated_manager_elevation(service):
    service.role_repo.get_by_name.return_value = SimpleNamespace(name="Unit Manager")
    service.repo.get_by_user_and_org.return_value = {"id": uuid.uuid4(), "is_active": True}
    with pytest.raises(ForbiddenError):
        await service.update_user_organization_role(
            uuid.uuid4(), uuid.uuid4(), "unit_manager", actor_id=uuid.uuid4()
        )
    service.repo.update.assert_not_awaited()


def test_search_route_forwards_actor_and_validates_limit(monkeypatch):
    controller = SimpleNamespace(
        get_assignable_users=AsyncMock(return_value={"users": [], "total": 0})
    )
    monkeypatch.setattr(
        user_organizations_route, "get_user_organization_controller", lambda: controller
    )
    app = FastAPI()
    app.include_router(user_organizations_route.router)
    actor, destination = uuid.uuid4(), uuid.uuid4()
    override_route_dependencies(app, lambda: str(actor))
    client = TestClient(app)
    response = client.get(f"/organizations/{destination}/assignable-users?query=alex&limit=10")
    assert response.status_code == 200
    controller.get_assignable_users.assert_awaited_once_with(destination, actor, "alex", 10)
    assert client.get(f"/organizations/{destination}/assignable-users?limit=101").status_code == 422


async def test_search_admin_without_literal_action_reaches_authoritative_service(
    service, monkeypatch
):
    import src.service as service_factories
    from src import repository
    from src.api import dependencies

    actor = uuid.uuid4()
    destination = service.scope_service.resolve.return_value.root_ids[0]
    service.scope_service.resolve.return_value = OrganizationScope(True, [])
    service.permission_resolver.resolve_effective_access.return_value = (["org:read"], True)
    resolver = SimpleNamespace(resolve_effective_permissions=AsyncMock(return_value=["org:read"]))
    monkeypatch.setattr(dependencies, "get_permission_resolver_service", lambda: resolver)
    monkeypatch.setattr(
        repository,
        "UserRepository",
        lambda: SimpleNamespace(get_by_id=AsyncMock(return_value=SimpleNamespace(id=actor))),
    )
    monkeypatch.setattr(
        service_factories, "get_audit_service", lambda: SimpleNamespace(log=AsyncMock())
    )
    # Keep route auth and service authorization real; only external identity/I/O is stubbed.
    monkeypatch.setattr(
        user_organizations_route,
        "get_user_organization_controller",
        lambda: SimpleNamespace(get_assignable_users=service.get_assignable_users),
    )
    service.user_repo.list_assignable.return_value = ([], 0)
    app = FastAPI()
    app.include_router(user_organizations_route.router)
    app.dependency_overrides[dependencies.require_auth] = lambda: str(actor)
    response = TestClient(app).get(f"/organizations/{destination}/assignable-users?query=yusuf")
    assert response.status_code == 200
    service.user_repo.list_assignable.assert_awaited_once()


async def test_search_nonadmin_without_action_is_denied(service):
    service.permission_resolver.resolve_effective_access.return_value = (["org:read"], False)
    with pytest.raises(ForbiddenError):
        await service.get_assignable_users(uuid.uuid4(), uuid.uuid4(), "yusuf")
    service.user_repo.list_assignable.assert_not_awaited()
