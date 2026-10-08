"""Lazy tree operations read their branch rather than the realm inventory."""

from collections import Counter
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from error_contract import NotFoundError
import pytest

from src.repository.organization_repository import OrganizationRepository
from tests.test_keycloak_organizations import CHILD, ROOT, Admin

LEAF = UUID(int=100)
SIBLING = UUID(int=101)
OUTSIDE = UUID(int=102)


@pytest.fixture
def admin():
    client = Admin()
    client.groups.update(
        {
            str(LEAF): {"id": str(LEAF), "name": "Leaf", "parentId": str(CHILD)},
            str(SIBLING): {
                "id": str(SIBLING),
                "name": "Sibling",
                "parentId": str(ROOT),
                "attributes": {
                    "agenticai.organization.order_index": ["-1"],
                    "agenticai.organization.is_active": ["false"],
                },
            },
            str(OUTSIDE): {"id": str(OUTSIDE), "name": "Outside"},
        }
    )
    counts = Counter(row.get("parentId") for row in client.groups.values())
    for group in client.groups.values():
        group["subGroupCount"] = counts[group["id"]]
    return client


@pytest.mark.asyncio
async def test_shallow_tree_reads_roots_and_one_level_only(admin):
    tree = await OrganizationRepository(admin).get_tree(max_depth=1)
    root = tree["roots"][0]
    assert [child["id"] for child in root["children"]] == [SIBLING, CHILD]
    assert not root["children"][0]["is_active"]
    child = root["children"][1]
    assert child["children"] == [] and child["children_count"] == 1
    assert child["path"] == f"/{ROOT}/" and child["level"] == 1
    paths = [path for _, path, _ in admin.calls]
    assert len(paths) == 2
    assert paths[0].startswith("/groups?") and "search=" not in paths[0]
    assert paths[1].startswith(f"/groups/{ROOT}/children?")


@pytest.mark.asyncio
async def test_rooted_tree_depth_is_relative_and_does_not_read_sibling_branch(admin):
    tree = await OrganizationRepository(admin).get_tree(root_id=CHILD, max_depth=1)
    assert tree["id"] == CHILD and tree["level"] == 1
    assert tree["children"][0]["id"] == LEAF
    assert tree["children"][0]["path"] == f"/{ROOT}/{CHILD}/"
    paths = [path for _, path, _ in admin.calls]
    assert paths == [f"/groups/{CHILD}", f"/groups/{ROOT}", paths[-1]]
    assert paths[-1].startswith(f"/groups/{CHILD}/children?")


@pytest.mark.asyncio
async def test_direct_children_and_ancestors_never_read_full_inventory(admin):
    repo = OrganizationRepository(admin)
    children = await repo.get_children(CHILD)
    assert [child["id"] for child in children] == [LEAF]
    assert len(admin.calls) == 3
    admin.calls.clear()
    ancestors = await repo.get_ancestors(LEAF)
    assert [ancestor["id"] for ancestor in ancestors] == [ROOT, CHILD]
    assert [path for _, path, _ in admin.calls] == [
        f"/groups/{LEAF}",
        f"/groups/{CHILD}",
        f"/groups/{ROOT}",
    ]


@pytest.mark.asyncio
async def test_missing_branch_keeps_existing_results(admin):
    repo = OrganizationRepository(admin)
    missing = uuid4()
    assert await repo.get_children(missing) == []
    assert await repo.get_ancestors(missing) == []
    with pytest.raises(NotFoundError):
        await repo.get_tree(root_id=missing, max_depth=1)
    assert all(path == f"/groups/{missing}" for _, path, _ in admin.calls)


@pytest.mark.asyncio
async def test_manager_roots_read_assigned_groups_and_shared_ancestors_only(admin):
    with patch(
        "src.repository.user_organization_repository.UserOrganizationRepository.get_active_unit_manager_organizations",
        AsyncMock(return_value=[{"organization_id": CHILD}, {"organization_id": SIBLING}]),
    ):
        roots = await OrganizationRepository(admin).get_manager_roots(uuid4())
    assert {root["id"] for root in roots} == {CHILD, SIBLING}
    assert all(root["path"] == f"/{ROOT}/" for root in roots)
    paths = [path for _, path, _ in admin.calls]
    assert len(paths) == 3 and paths.count(f"/groups/{ROOT}") == 1
    assert not any(path.startswith("/groups?") for path in paths)


@pytest.mark.asyncio
async def test_direct_child_pages_preserve_all_items_without_leaf_reads(admin):
    for number in range(1000, 2003):
        identity = str(UUID(int=number))
        admin.groups[identity] = {
            "id": identity,
            "name": identity,
            "parentId": str(CHILD),
            "subGroupCount": 0,
        }
    admin.groups[str(CHILD)]["subGroupCount"] = 1004
    rows = await OrganizationRepository(admin).get_children(CHILD)
    assert len(rows) == 1004
    paths = [path for _, path, _ in admin.calls]
    assert len(paths) == 4
    assert all(path.startswith(f"/groups/{CHILD}/children?") for path in paths[2:])


@pytest.mark.asyncio
async def test_zero_depth_keeps_unexpanded_root_counts(admin):
    root = await OrganizationRepository(admin).get_tree(root_id=CHILD, max_depth=0)
    assert root["children"] == [] and root["children_count"] == 1
    assert len(admin.calls) == 2
