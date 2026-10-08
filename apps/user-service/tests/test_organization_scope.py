"""Delegated scope is independent of broad action permissions."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.exceptions import ForbiddenError
from src.service.organization_scope_service import OrganizationScopeService


@pytest.fixture
def scope_service():
    service = OrganizationScopeService()
    service.resolver = SimpleNamespace(
        resolve_effective_access=AsyncMock(
            return_value=(["org:list", "org:read", "org:update"], False)
        )
    )
    service.repo = SimpleNamespace(get_manager_roots=AsyncMock(return_value=[]))
    return service


async def test_action_permissions_without_assignment_have_empty_scope(scope_service):
    scope = await scope_service.resolve(uuid.uuid4())
    assert not scope.global_access
    assert not scope.contains({"id": uuid.uuid4(), "path": "/"})


async def test_nested_assignments_are_collapsed_and_siblings_excluded(scope_service):
    ancestor, root, child, other = [uuid.uuid4() for _ in range(4)]
    scope_service.repo.get_manager_roots.return_value = [
        {"id": root, "path": f"/{ancestor}/", "level": 1},
        {"id": child, "path": f"/{ancestor}/{root}/", "level": 2},
    ]
    scope = await scope_service.resolve(uuid.uuid4())
    assert scope.root_ids == [root]
    assert scope.contains({"id": child, "path": f"/{ancestor}/{root}/"})
    assert not scope.contains({"id": ancestor, "path": "/"})
    assert not scope.contains({"id": other, "path": f"/{ancestor}/"})
    public_root = scope.present(
        {"id": root, "path": f"/{ancestor}/", "parent_id": ancestor, "level": 1}
    )
    assert public_root["parent_id"] is None
    assert public_root["path"] == "/"
    assert public_root["level"] == 0
    with pytest.raises(ForbiddenError):
        scope.require_mutable_root(root)


async def test_authoritative_admin_access_is_global(scope_service):
    scope_service.resolver.resolve_effective_access.return_value = (["org:read"], True)
    scope = await scope_service.resolve(uuid.uuid4())
    assert scope.global_access
    assert scope.contains({"id": uuid.uuid4(), "path": "/"})
    scope_service.repo.get_manager_roots.assert_not_awaited()


async def test_multiple_disjoint_units_remain_roots(scope_service):
    roots = [uuid.uuid4(), uuid.uuid4()]
    scope_service.repo.get_manager_roots.return_value = [
        {"id": root, "path": "/", "level": 0} for root in roots
    ]
    assert (await scope_service.resolve(uuid.uuid4())).root_ids == roots
