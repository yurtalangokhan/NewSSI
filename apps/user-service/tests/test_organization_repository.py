"""Organization repository contracts against a simulated Keycloak admin API."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import httpx
from error_contract import NotFoundError
import pytest

from src.core.exceptions import ConflictError
from src.repository.organization_repository import OrganizationRepository
from tests.test_keycloak_organizations import CHILD, ROOT, Admin


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["load test 00092", "00092 load", "  load   test 00092 "])
async def test_search_matches_all_words_instead_of_a_contiguous_phrase(query):
    admin = Admin()
    admin.groups[str(CHILD)]["name"] = "Load Test Group 00092"
    assert [g["id"] for g in await OrganizationRepository(admin).search(query)] == [CHILD]


@pytest.mark.asyncio
async def test_create_root_and_child_preserves_metadata():
    admin = Admin()
    admin.groups.clear()
    repo = OrganizationRepository(admin)
    root = await repo.create("Enterprise", "ROOT", metadata={"nested": {"key": 7}})
    child = await repo.create("Department", "DEPT", parent_id=root["id"], created_by=ROOT)
    assert child["path"] == f"/{root['id']}/"
    assert child["created_by"] == ROOT
    assert root["metadata"] == {"nested": {"key": 7}}
    assert root["created_at"]
    with pytest.raises(ConflictError):
        await repo.create("Second root", "SECOND")
    with pytest.raises(ConflictError):
        await repo.create("Duplicate", "DEPT", parent_id=root["id"])
    with pytest.raises(NotFoundError):
        await repo.create("Orphan", "ORPHAN", parent_id=uuid4())


@pytest.mark.asyncio
async def test_update_preserves_external_attributes_and_roundtrips_fields():
    admin = Admin()
    admin.groups[str(CHILD)]["attributes"] = {"external": ["kept"]}
    repo = OrganizationRepository(admin)

    async def project(mutation):
        return await mutation()

    with patch(
        "src.repository.keycloak_resource_authorization.project_resource_permission_mutation",
        AsyncMock(side_effect=project),
    ) as projection:
        result = await repo.update(
            CHILD,
            name="New",
            code="NEW",
            metadata={"color": "green"},
            is_active=False,
            order_index=9,
        )
    projection.assert_awaited_once()
    assert result["code"] == "NEW"
    assert result["metadata"] == {"color": "green"}
    assert result["order_index"] == 9
    assert admin.groups[str(CHILD)]["attributes"]["external"] == ["kept"]
    assert await repo.list_all(is_active=True) == ([await repo.get_by_id(ROOT)], 1)
    assert await repo.get_by_id(uuid4()) is None
    assert await repo.update(uuid4(), name="Missing") is None


@pytest.mark.asyncio
async def test_paginated_children_counts_tree_depth_and_ancestors():
    admin = Admin()
    for i in range(10, 115):
        group_id = str(UUID(int=i))
        admin.groups[group_id] = {"id": group_id, "name": str(i), "parentId": str(ROOT)}
    repo = OrganizationRepository(admin)
    children = await repo.get_children(ROOT)
    assert len(children) == 106
    assert any(path.startswith(f"/groups/{ROOT}/children?") for _, path, _ in admin.calls)
    assert not any(path.startswith("/groups?") for _, path, _ in admin.calls)
    assert not any("partial-export" in path for _, path, _ in admin.calls)
    assert (await repo.get_ancestors(CHILD))[0]["id"] == ROOT
    items, total = await repo.list_all(skip=105, limit=1, parent_id=ROOT)
    assert len(items) == 1 and total == 106
    assert (await repo.get_tree(max_depth=0))["roots"][0]["children_count"] == 106


@pytest.mark.asyncio
async def test_delete_cleans_subtree_resource_grants():
    repo = OrganizationRepository(Admin())
    cleanup = AsyncMock(return_value=1)

    async def project(mutation):
        return await mutation()

    with (
        patch(
            "src.repository.resource_permission_repository.ResourcePermissionRepository.delete_organization_permissions",
            cleanup,
        ),
        patch(
            "src.repository.keycloak_resource_authorization.project_resource_permission_mutation",
            AsyncMock(side_effect=project),
        ) as projection,
    ):
        assert await repo.delete(ROOT)
    assert {call.args[0] for call in cleanup.call_args_list} == {ROOT, CHILD}
    assert await repo.get_by_id(CHILD) is None
    assert projection.await_count == 1


@pytest.mark.asyncio
async def test_ten_thousand_organizations_skip_leaf_queries():
    admin = Admin()
    for index in range(10, 10008):
        group_id = str(UUID(int=index))
        admin.groups[group_id] = {
            "id": group_id,
            "name": f"Department {index}",
            "parentId": str(ROOT),
        }
    organizations, total = await OrganizationRepository(admin).list_all(skip=9990, limit=10)
    assert total == 10000
    assert len(organizations) == 10
    assert all(org["level"] == 1 and org["path"] == f"/{ROOT}/" for org in organizations)
    assert len(admin.calls) == 11
    assert all(method == "GET" for method, _, _ in admin.calls)
    assert all(
        path.startswith("/groups?") or path == "/groups/count?top=false"
        for _, path, _ in admin.calls
    )


@pytest.mark.asyncio
async def test_missing_child_counts_are_derived_from_complete_inventory():
    class UnknownCounts(Admin):
        async def _keycloak_request(self, method, path, **kwargs):
            response = await super()._keycloak_request(method, path, **kwargs)
            data = response.json()
            if isinstance(data, list):
                data = [
                    {key: value for key, value in group.items() if key != "subGroupCount"}
                    for group in data
                ]
            return httpx.Response(response.status_code, json=data, request=response.request)

    admin = UnknownCounts()
    groups, count = await OrganizationRepository(admin).list_all()
    assert count == 2
    assert groups[1]["parent_id"] == ROOT
    assert len(admin.calls) == 2
    assert not any("/children" in path for _, path, _ in admin.calls)


@pytest.mark.asyncio
async def test_group_inventory_reuses_one_admin_scope_for_all_pages():
    from src.repository.keycloak_group_inventory import read_group_inventory

    class ScopedAdmin(Admin):
        entered = 0
        active = False

        @asynccontextmanager
        async def admin_request_scope(self):
            self.entered += 1
            self.active = True
            try:
                yield
            finally:
                self.active = False

        async def _keycloak_request(self, method, path, **kwargs):
            assert self.active
            return await super()._keycloak_request(method, path, **kwargs)

    admin = ScopedAdmin()
    groups = await read_group_inventory(admin, page_size=1)
    assert len(groups) == 2
    assert admin.entered == 1
    assert not admin.active
    assert len(admin.calls) == 3


@pytest.mark.asyncio
async def test_single_group_reads_only_its_parent_chain_and_preserves_counts():
    from tests.test_keycloak_organizations import USER

    admin = Admin()
    admin.groups[str(USER)] = {"id": str(USER), "name": "Leaf", "parentId": str(CHILD)}
    for group in admin.groups.values():
        group["subGroupCount"] = 0 if group["id"] == str(USER) else 1
    repo = OrganizationRepository(admin)
    leaf = await repo.get_by_id(USER)
    assert leaf["path"] == f"/{ROOT}/{CHILD}/"
    assert leaf["level"] == 2 and leaf["parent_id"] == CHILD
    assert leaf["children_count"] == 0 and not leaf["has_children"]
    assert [path for _, path, _ in admin.calls] == [
        f"/groups/{USER}",
        f"/groups/{CHILD}",
        f"/groups/{ROOT}",
    ]
    admin.calls.clear()
    missing = uuid4()
    assert await repo.get_by_id(missing) is None
    assert [path for _, path, _ in admin.calls] == [f"/groups/{missing}"]


@pytest.mark.asyncio
async def test_user_memberships_resolve_only_relevant_groups_and_share_ancestors():
    import json

    from src.repository.user_organization_repository import MEMBERSHIPS, UserOrganizationRepository
    from tests.test_keycloak_organizations import USER

    admin = Admin()
    inactive = uuid4()
    admin.groups[str(inactive)] = {
        "id": str(inactive),
        "name": "Old",
        "parentId": str(ROOT),
        "subGroupCount": 0,
    }
    admin.groups[str(ROOT)]["subGroupCount"] = 2
    admin.groups[str(CHILD)]["subGroupCount"] = 0
    admin.users[str(USER)]["attributes"][MEMBERSHIPS] = [json.dumps({str(inactive): {}})]
    repo = UserOrganizationRepository(admin)
    active = await repo.get_user_organizations(USER)
    assert [item["organization_id"] for item in active] == [CHILD]
    assert f"/groups/{inactive}" not in [path for _, path, _ in admin.calls]
    admin.calls.clear()
    memberships = await repo.get_user_organizations(USER, include_inactive=True)
    assert {item["organization_id"]: item["is_active"] for item in memberships} == {
        CHILD: True,
        inactive: False,
    }
    paths = [path for _, path, _ in admin.calls]
    assert paths.count(f"/groups/{ROOT}") == 1
    assert not any(path.startswith("/groups?") or "/children" in path for path in paths)


@pytest.mark.asyncio
async def test_single_user_lookup_uses_scope_and_filters_disabled_organizations():
    from src.repository.user_organization_repository import UserOrganizationRepository
    from tests.test_keycloak_organizations import USER

    class ScopedAdmin(Admin):
        depth = 0

        @asynccontextmanager
        async def admin_request_scope(self):
            self.depth += 1
            try:
                yield
            finally:
                self.depth -= 1

        async def _keycloak_request(self, method, path, **kwargs):
            assert self.depth > 0
            return await super()._keycloak_request(method, path, **kwargs)

    admin = ScopedAdmin()
    admin.groups[str(CHILD)]["attributes"] = {"agenticai.organization.is_active": ["false"]}
    repo = UserOrganizationRepository(admin)
    assert await repo.get_user_organizations(USER) == []
    assert len(await repo.get_user_organizations(USER, include_inactive=True)) == 1
    assert admin.depth == 0
