import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.exceptions import ForbiddenError
from src.service.user_organization_service import UserOrganizationService


@pytest.fixture
def service():
    service = UserOrganizationService()
    service._require_management_scope = AsyncMock()
    service.role_repo = SimpleNamespace(
        get_by_name=AsyncMock(return_value=SimpleNamespace(name="Unit Manager"))
    )
    service.user_role_repo = SimpleNamespace(
        get_primary_roles=AsyncMock(return_value={}),
        list_user_roles=AsyncMock(return_value=[]),
    )
    service.user_service = SimpleNamespace(
        set_user_role=AsyncMock(return_value={"role": "Unit Manager"})
    )
    service.permission_resolver = SimpleNamespace(
        resolve_effective_access=AsyncMock(return_value=([], True))
    )
    return service


async def test_members_use_primary_assignment_not_legacy_or_mirror(service):
    uid, oid = uuid.uuid4(), uuid.uuid4()
    service.repo = SimpleNamespace(
        get_organization_users=AsyncMock(
            return_value=[
                {
                    "user_id": uid,
                    "organization_id": oid,
                    "role_in_org": "unit_manager",
                    "user": {"id": uid, "role": "system-admin"},
                }
            ]
        )
    )
    service.user_role_repo.get_primary_roles.return_value = {uid: "enduser"}
    result = await service.get_organization_users(oid)
    assert result[0]["role_in_org"] == "enduser"
    assert result[0]["user"]["role"] == "enduser"


async def test_change_role_uses_user_service_and_does_not_write_membership_role(service):
    uid, oid, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    service.repo = SimpleNamespace(
        get_by_user_and_org=AsyncMock(return_value={"id": uuid.uuid4(), "user_id": uid}),
        update=AsyncMock(),
    )
    result = await service.update_user_organization_role(uid, oid, "unit_manager", actor)
    service.user_service.set_user_role.assert_awaited_once_with(uid, "Unit Manager")
    service.repo.update.assert_not_awaited()
    assert result["role_in_org"] == "Unit Manager"


async def test_delegate_cannot_demote_a_globally_privileged_user(service):
    service.permission_resolver.resolve_effective_access.return_value = (
        ["org:manage-users"],
        False,
    )
    service.user_role_repo.list_user_roles.return_value = [
        {"name": "enterprise-admin", "is_primary": True}
    ]
    with pytest.raises(ForbiddenError):
        await service._require_delegable_role(uuid.uuid4(), uuid.uuid4(), "enduser")


@pytest.mark.parametrize(
    "repository_class,method",
    [
        ("OrganizationRepository", "get_manager_roots"),
        ("UserOrganizationRepository", "get_active_unit_manager_organizations"),
    ],
)
async def test_scope_queries_use_platform_assignment(repository_class, method, monkeypatch):
    import src.repository as repositories
    from tests.test_keycloak_organizations import CHILD, USER, Admin

    lookup = AsyncMock(return_value=[{"name": "Unit Manager", "is_primary": False}])
    monkeypatch.setattr(repositories.UserRoleRepository, "list_user_roles", lookup)
    repository = getattr(repositories, repository_class)(Admin())
    results = await getattr(repository, method)(USER)
    assert len(results) == 1
    assert results[0].get("organization_id", results[0]["id"]) == CHILD
    lookup.return_value = [{"name": "enduser", "is_primary": True}]
    assert await getattr(repository, method)(USER) == []


async def test_primary_role_lookup_deduplicates_users_and_uses_primary_assignment():
    from src.repository import UserRoleRepository

    repository = UserRoleRepository()
    user_id = uuid.uuid4()
    repository.client.request = AsyncMock(
        side_effect=[
            {"attributes": {"agentic.primary_role": ["Unit Manager"]}},
            [{"name": "enduser"}, {"name": "Unit Manager"}],
        ]
    )
    assert await repository.get_primary_roles([user_id, user_id]) == {user_id: "Unit Manager"}
    assert repository.client.request.await_count == 2


async def test_add_user_writes_global_role_and_membership_without_role_copy(service):
    uid, oid, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    service.user_repo = SimpleNamespace(get_by_id=AsyncMock(return_value=SimpleNamespace(id=uid)))
    service.org_repo = SimpleNamespace(get_by_id=AsyncMock(return_value={"id": oid}))
    service.repo = SimpleNamespace(
        get_by_user_and_org=AsyncMock(return_value=None),
        create=AsyncMock(
            return_value={"user_id": uid, "organization_id": oid, "role_in_org": "member"}
        ),
    )
    result = await service.assign_user_to_organization(uid, oid, "unit_manager", assigned_by=actor)
    service.user_service.set_user_role.assert_awaited_once_with(uid, "Unit Manager")
    assert "role_in_org" not in service.repo.create.call_args.kwargs
    assert result["role_in_org"] == "Unit Manager"


async def test_delegated_end_user_assignment_remains_allowed(service):
    service.permission_resolver.resolve_effective_access.return_value = (
        ["org:manage-users"],
        False,
    )
    service.user_role_repo.list_user_roles.return_value = [{"name": "enduser", "is_primary": True}]
    await service._require_delegable_role(uuid.uuid4(), uuid.uuid4(), "enduser")
