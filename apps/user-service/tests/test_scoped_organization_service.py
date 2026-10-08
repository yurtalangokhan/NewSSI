"""Subtree reads and writes cannot escape the delegated boundary."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.exceptions import ForbiddenError
from src.service.organization_scope_service import OrganizationScope
from src.service.scoped_organization_service import ScopedOrganizationService


@pytest.fixture
def scoped():
    actor, ancestor, root, child, sibling = [uuid.uuid4() for _ in range(5)]
    nodes = {
        root: {"id": root, "parent_id": ancestor, "path": f"/{ancestor}/", "level": 1},
        child: {"id": child, "parent_id": root, "path": f"/{ancestor}/{root}/", "level": 2},
        sibling: {"id": sibling, "parent_id": ancestor, "path": f"/{ancestor}/", "level": 1},
    }
    raw = SimpleNamespace(
        get_organization=AsyncMock(side_effect=lambda oid: nodes.get(oid)),
        get_organization_tree=AsyncMock(return_value={**nodes[root], "children": [nodes[child]]}),
        create_organization=AsyncMock(),
        update_organization=AsyncMock(),
        move_organization=AsyncMock(),
        delete_organization=AsyncMock(),
    )
    service = ScopedOrganizationService(actor, raw)
    service.scope_service = SimpleNamespace(
        resolve=AsyncMock(return_value=OrganizationScope(False, [nodes[root]]))
    )
    return service, raw, root, child, sibling


async def test_tree_starts_at_assigned_unit(scoped):
    service, raw, root, child, _ = scoped
    result = await service.get_organization_tree(None, 2)
    assert result["roots"][0]["id"] == root
    assert result["roots"][0]["parent_id"] is None
    assert result["roots"][0]["children"][0]["id"] == child
    raw.get_organization_tree.assert_awaited_once_with(root, 2)


async def test_scoped_search_matches_separated_words(scoped):
    service, _, root, child, _ = scoped
    nodes = [
        {
            "id": child,
            "parent_id": root,
            "path": f"/{root}/",
            "level": 2,
            "name": "Load Test Unit 00092",
        },
        {"id": root, "parent_id": None, "path": "/", "level": 1, "name": "Load Test Unit 00093"},
    ]
    service.repo.get_scoped_organizations = AsyncMock(return_value=nodes)
    results = await service.search_organizations("load test 00092", 100)
    assert [node["id"] for node in results] == [child]
    service.repo.get_scoped_organizations.assert_awaited_once_with([root])


async def test_forbidden_reads_and_writes_do_not_reach_mutation(scoped):
    service, raw, root, child, sibling = scoped
    with pytest.raises(ForbiddenError):
        await service.get_organization(sibling)
    with pytest.raises(ForbiddenError):
        await service.update_organization(sibling, name="other")
    with pytest.raises(ForbiddenError):
        await service.move_organization(child, sibling)
    with pytest.raises(ForbiddenError):
        await service.move_organization(root, child)
    with pytest.raises(ForbiddenError):
        await service.delete_organization(root, cascade=True)
    with pytest.raises(ForbiddenError):
        await service.create_organization(name="root", code="new", parent_id=None)
    raw.update_organization.assert_not_awaited()
    raw.move_organization.assert_not_awaited()
    raw.delete_organization.assert_not_awaited()
    raw.create_organization.assert_not_awaited()


async def test_create_child_in_scope(scoped):
    service, raw, root, child, _ = scoped
    raw.create_organization.return_value = {
        "id": child,
        "parent_id": root,
        "path": f"/{root}/",
        "level": 2,
    }
    await service.create_organization(name="child", code="new", parent_id=root)
    raw.create_organization.assert_awaited_once()
