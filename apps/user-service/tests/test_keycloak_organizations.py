"""Keycloak organization and membership adapter contracts."""

from collections import Counter
from copy import deepcopy
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import httpx
from error_contract import BadRequestError, DependencyUnavailableError
import pytest

from src.repository.keycloak_group_client import KeycloakGroupClient
from src.repository.organization_repository import OrganizationRepository
from src.repository.user_organization_repository import UserOrganizationRepository
from tests.fakes.keycloak_users import put_user

ROOT = UUID(int=1)
CHILD = UUID(int=2)
USER = UUID(int=3)


class Admin:
    def __init__(self):
        self.groups = {
            str(ROOT): {"id": str(ROOT), "name": "Root"},
            str(CHILD): {"id": str(CHILD), "name": "Child", "parentId": str(ROOT)},
        }
        self.users = {
            str(USER): {
                "id": str(USER),
                "username": "alice",
                "email": "alice@example.test",
                "firstName": "Alice",
                "lastName": "\u00d6zt\u00fcrk",
                "attributes": {},
            }
        }
        self.members = {str(USER): {str(CHILD)}}
        self.calls = []

    async def _keycloak_request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        url = urlsplit(path)
        parts = url.path.strip("/").split("/")
        data = None
        status = 200
        if method == "GET":
            if parts == ["groups"]:
                data = [
                    g
                    for g in self.groups.values()
                    if "search" in parse_qs(url.query, keep_blank_values=True)
                    or not g.get("parentId")
                ]
            elif parts == ["groups", "count"]:
                data = {"count": len(self.groups)}
            elif len(parts) == 3 and parts[2] == "children":
                data = [g for g in self.groups.values() if g.get("parentId") == parts[1]]
            elif parts == ["users"]:
                data = list(self.users.values())
            elif len(parts) == 3 and parts[2] == "groups":
                data = [self.groups[g] for g in self.members[parts[1]]]
            elif len(parts) == 3 and parts[2] == "members":
                data = [self.users[u] for u, gs in self.members.items() if parts[1] in gs]
            else:
                data = (self.groups if parts[0] == "groups" else self.users).get(parts[1])
                if data is None:
                    status = 404
            if isinstance(data, list):
                if parts[0] == "groups":
                    counts = Counter(g.get("parentId") for g in self.groups.values())
                    data = [{**group, "subGroupCount": counts[group["id"]]} for group in data]
                first = int(parse_qs(url.query).get("first", [0])[0])
                size = int(parse_qs(url.query).get("max", [100])[0])
                data = data[first : first + size]
        elif len(parts) == 4 and parts[0] == "users":
            if method == "PUT":
                self.members[parts[1]].add(parts[3])
            else:
                self.members[parts[1]].discard(parts[3])
            status = 204
        elif method == "PUT" and parts[0] == "users":
            put_user(self.users[parts[1]], kwargs["json"])
            status = 204
        elif method == "PUT":
            self.groups[parts[1]].update(kwargs["json"])
            status = 204
        elif method == "POST" and parts == ["partial-export"]:
            children_by_parent = {}
            for group in self.groups.values():
                children_by_parent.setdefault(group.get("parentId"), []).append(group)

            def tree(group):
                return {
                    **group,
                    "subGroups": [tree(child) for child in children_by_parent.get(group["id"], [])],
                }

            data = {"groups": [tree(group) for group in children_by_parent.get(None, [])]}
        elif method == "POST":
            payload = deepcopy(kwargs["json"])
            group_id = payload.setdefault("id", str(uuid4()))
            self.groups.setdefault(group_id, {}).update(payload)
            self.groups[group_id]["parentId"] = parts[1] if len(parts) == 3 else None
            status = 204
        elif method == "DELETE" and parts[0] == "groups":
            pending = [parts[1]]
            while pending:
                group_id = pending.pop()
                pending.extend(
                    g["id"] for g in self.groups.values() if g.get("parentId") == group_id
                )
                self.groups.pop(group_id, None)
                for group_ids in self.members.values():
                    group_ids.discard(group_id)
            status = 204
        return httpx.Response(
            status, json=deepcopy(data), request=httpx.Request(method, "https://kc" + path)
        )


@pytest.mark.asyncio
async def test_existing_groups_preserve_ids_hierarchy_and_scope():
    repo = OrganizationRepository(Admin())
    tree = await repo.get_tree()
    child = tree["roots"][0]["children"][0]
    assert child["id"] == CHILD
    assert child["path"] == f"/{ROOT}/"
    assert child["parent_id"] == ROOT
    assert [o["id"] for o in await repo.get_scoped_organizations([CHILD])] == [CHILD]
    assert (await repo.get_tree(max_depth=0))["roots"][0]["has_children"]


@pytest.mark.asyncio
async def test_move_rejects_cycles_without_mutation():
    admin = Admin()
    repo = OrganizationRepository(admin)
    with pytest.raises(BadRequestError):
        await repo.move_organization(ROOT, CHILD)
    assert all(
        method == "GET" or path.startswith("/partial-export") for method, path, _ in admin.calls
    )


@pytest.mark.asyncio
async def test_membership_primary_and_deactivation_preserve_unrelated_attributes():
    admin = Admin()
    admin.users[str(USER)]["attributes"]["external"] = ["kept"]
    repo = UserOrganizationRepository(admin)
    original = await repo.get_by_user_and_org(USER, CHILD)
    assert original["user"]["username"] == "alice"
    await repo.create(USER, ROOT, is_primary=True)
    assert (await repo.get_primary_organization(USER))["organization_id"] == ROOT
    await repo.set_primary(USER, CHILD)
    assert sum(m["is_primary"] for m in await repo.get_user_organizations(USER)) == 1
    await repo.update(original["id"], is_active=False)
    assert str(CHILD) not in admin.members[str(USER)]
    assert len(await repo.get_user_organizations(USER, include_inactive=True)) == 2
    assert admin.users[str(USER)]["attributes"]["external"] == ["kept"]


@pytest.mark.asyncio
async def test_group_errors_propagate():
    class Broken(Admin):
        async def _keycloak_request(self, method, path, **kwargs):
            return httpx.Response(503, request=httpx.Request(method, "https://kc" + path))

    with pytest.raises(DependencyUnavailableError):
        await OrganizationRepository(Broken()).list_all()


@pytest.mark.asyncio
async def test_known_membership_update_never_scans_user_directory():
    admin = Admin()
    repo = UserOrganizationRepository(admin)
    original = await repo.get_by_user_and_org(USER, CHILD)
    updated = await repo.update_by_user_and_org(USER, CHILD, is_primary=True)
    assert updated["id"] == original["id"] and updated["is_primary"]
    assert not any(path.startswith("/users?") for _, path, _ in admin.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("DELETE", f"/users/{USER}/groups/{CHILD}", None),
        ("POST", f"/groups/{ROOT}/children", {"id": str(CHILD), "name": "Child"}),
        ("DELETE", f"/groups/{CHILD}", None),
        ("PUT", f"/users/{USER}", {"attributes": {}}),
    ],
)
async def test_identity_mutations_immediately_invalidate_cached_access(method, path, payload):
    from src.service.permission_resolver_service import get_permission_resolver_service

    resolver = get_permission_resolver_service()
    resolver._cache_access(USER, ["*"], True)
    assert USER in resolver._cache
    kwargs = {"json": payload} if payload is not None else {}
    await KeycloakGroupClient(Admin()).request(method, path, **kwargs)
    assert USER not in resolver._cache


@pytest.mark.asyncio
async def test_reads_and_failed_mutations_do_not_invalidate_access_cache():
    from src.service.permission_resolver_service import get_permission_resolver_service

    resolver = get_permission_resolver_service()
    resolver._cache_access(USER, ["chat:read"], False)
    await KeycloakGroupClient(Admin()).get(f"/groups/{CHILD}")
    assert USER in resolver._cache

    class Broken(Admin):
        async def _keycloak_request(self, method, path, **kwargs):
            return httpx.Response(503, request=httpx.Request(method, "https://kc" + path))

    with pytest.raises(DependencyUnavailableError):
        await KeycloakGroupClient(Broken()).request("DELETE", f"/groups/{CHILD}")
    assert USER in resolver._cache
    resolver._cache.clear()
