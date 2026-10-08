"""Bulk read-back inventory must match effective Keycloak identity semantics."""

import asyncio
from copy import deepcopy
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from src.service.keycloak_cutover_inventory import KeycloakCutoverInventory


class InventoryAdmin:
    def __init__(self):
        self.calls = []
        self.users = [
            {"id": f"u{i}", "username": f"user{i}", "attributes": {"kept": ["yes"]}}
            for i in range(1002)
        ]
        self.export = {
            "groups": [
                {
                    "id": "g1",
                    "name": "Root",
                    "realmRoles": ["manager"],
                    "subGroups": [{"id": "g2", "name": "Child", "attributes": {"code": ["C"]}}],
                }
            ],
            "roles": {
                "realm": [
                    {
                        "id": "r1",
                        "name": "manager",
                        "composite": True,
                        "composites": {"realm": ["reader"]},
                    },
                    {"id": "r2", "name": "reader"},
                ],
                "client": {
                    "service": [
                        {
                            "id": "cr1",
                            "name": "client-manager",
                            "clientRole": True,
                            "composite": True,
                            "composites": {"realm": ["manager"]},
                        }
                    ]
                },
            },
            "clients": [{"id": "client-id", "clientId": "service", "secret": "discard-me"}],
        }

    async def _keycloak_request(self, method, path, **kwargs):
        self.calls.append((method, path, deepcopy(kwargs)))
        parsed = urlsplit(path)
        query = {
            **parse_qs(parsed.query),
            **{k: [str(v)] for k, v in kwargs.get("params", {}).items()},
        }
        if parsed.path == "/partial-export":
            return httpx.Response(500, request=httpx.Request(method, "https://kc" + path))
        elif method == "PUT" and parsed.path.startswith("/users/"):
            user = next(u for u in self.users if u["id"] == parsed.path.split("/")[2])
            user.update(kwargs["json"])
            return httpx.Response(204, request=httpx.Request(method, "https://kc" + path))
        elif method == "PUT" and parsed.path == "/groups/g2":
            self.export["groups"][0]["subGroups"][0].update(kwargs["json"])
            return httpx.Response(204, request=httpx.Request(method, "https://kc" + path))
        else:

            def group_row(group):
                return {
                    **{key: value for key, value in group.items() if key != "subGroups"},
                    "subGroupCount": len(group.get("subGroups", [])),
                    "realmRoles": group.get("realmRoles", []),
                    "clientRoles": group.get("clientRoles", {}),
                }

            realm = self.export["roles"]["realm"]
            client_roles = self.export["roles"]["client"]["service"]
            data = {
                "/users": self.users,
                "/users/count": len(self.users),
                "/groups/count": {"count": 2},
                "/groups": [group_row(g) for g in self.export["groups"]]
                + [
                    {**group_row(g), "parentId": "g1"}
                    for g in self.export["groups"][0]["subGroups"]
                ],
                "/groups/g1/children": [
                    group_row(g) for g in self.export["groups"][0]["subGroups"]
                ],
                "/groups/g2/children": [],
                "/roles": [{k: v for k, v in r.items() if k != "composites"} for r in realm],
                "/clients": self.export["clients"],
                "/clients/client-id/roles": [
                    {k: v for k, v in r.items() if k != "composites"} for r in client_roles
                ],
                "/groups/g1/members": [],
                "/groups/g2/members": [self.users[0]],
                "/roles/manager/users": [self.users[1]],
                "/roles/reader/users": [],
                "/clients/client-id/roles/client-manager/users": [self.users[2]],
                "/unsupported": {"live": True},
            }.get(parsed.path)
            if parsed.path.startswith("/roles-by-id/"):
                role = next(r for r in realm + client_roles if r["id"] == parsed.path.split("/")[2])
                data = [
                    next((r for r in realm if r["name"] == name), {"id": "missing", "name": name})
                    for name in role.get("composites", {}).get("realm", [])
                ]
        if isinstance(data, list):
            first = int(query.get("first", [0])[0])
            maximum = int(query.get("max", [1000])[0])
            data = data[first : first + maximum]
        return httpx.Response(
            200 if data is not None else 404,
            json=deepcopy(data),
            request=httpx.Request(method, "https://kc" + path),
        )


@pytest.mark.asyncio
async def test_bulk_inventory_indexes_full_profiles_groups_and_effective_realm_roles():
    admin = InventoryAdmin()
    inventory = await KeycloakCutoverInventory.load(admin)
    initial = len(admin.calls)
    for index in range(1002):
        profile = await inventory._keycloak_request("GET", f"/users/u{index}")
        assert profile.json()["attributes"] == {"kept": ["yes"]}
    groups = (await inventory._keycloak_request("GET", "/users/u0/groups?first=0&max=100")).json()
    assert [g["id"] for g in groups] == ["g2"]
    assert groups[0]["parentId"] == "g1"
    assert groups[0]["path"] == "/Root/Child"
    for index in (0, 1, 2):
        roles = (
            await inventory._keycloak_request(
                "GET", f"/users/u{index}/role-mappings/realm/composite"
            )
        ).json()
        assert {r["name"] for r in roles} == {"manager", "reader"}
    assert len(admin.calls) == initial
    assert not any("partial-export" in path for _, path, _ in admin.calls)
    assert (await inventory._keycloak_request("GET", "/users/missing")).status_code == 404
    assert any(
        "first=1000" in path or args.get("params", {}).get("first") == 1000
        for _, path, args in admin.calls
    )


@pytest.mark.asyncio
async def test_metadata_write_refreshes_batched_profiles_from_actual_readback():
    admin = InventoryAdmin()
    inventory = await KeycloakCutoverInventory.load(admin)
    await inventory._keycloak_request("PUT", "/users/u0", json={"attributes": {"changed": ["yes"]}})
    # Readback, not the submitted payload, remains authoritative.
    admin.users[0]["attributes"]["server"] = ["added"]
    profile = (await inventory._keycloak_request("GET", "/users/u0")).json()
    assert profile["attributes"] == {"changed": ["yes"], "server": ["added"]}
    assert not any(method == "GET" and path == "/users/u0" for method, path, _ in admin.calls)


@pytest.mark.asyncio
async def test_unknown_paths_warn_and_fall_through(caplog):
    inventory = await KeycloakCutoverInventory.load(InventoryAdmin())
    response = await inventory._keycloak_request("GET", "/unsupported")
    assert response.json() == {"live": True}
    assert "falling through" in caplog.text


@pytest.mark.asyncio
async def test_incomplete_snapshot_fails_closed():
    admin = InventoryAdmin()
    admin.export["roles"]["realm"][0]["composites"]["realm"] = ["missing-role"]
    with pytest.raises(ValueError, match="role"):
        await KeycloakCutoverInventory.load(admin)


@pytest.mark.asyncio
async def test_group_metadata_reload_does_not_repeat_membership_inventory():
    admin = InventoryAdmin()
    inventory = await KeycloakCutoverInventory.load(admin)
    before = len(admin.calls)
    await inventory._keycloak_request(
        "PUT",
        "/groups/g2",
        json={
            "name": "Child",
            "attributes": {"metadata": ["new"]},
        },
    )
    group = (await inventory._keycloak_request("GET", "/groups/g2")).json()
    assert group["attributes"] == {"metadata": ["new"]}
    assert not any("/members" in path or "/users?" in path for _, path, _ in admin.calls[before:])


@pytest.mark.asyncio
async def test_reserved_collection_routes_fall_through_instead_of_missing_identity():
    inventory = await KeycloakCutoverInventory.load(InventoryAdmin())
    response = await inventory._keycloak_request("GET", "/users/count")
    assert response.status_code == 200
    assert response.json() == 1002


@pytest.mark.asyncio
async def test_membership_and_role_pages_include_users_after_first_thousand():
    class LargeAssignments(InventoryAdmin):
        async def _keycloak_request(self, method, path, **kwargs):
            parsed = urlsplit(path)
            if method == "GET" and parsed.path in {"/groups/g2/members", "/roles/reader/users"}:
                self.calls.append((method, path, deepcopy(kwargs)))
                query = parse_qs(parsed.query)
                first = int(query["first"][0])
                maximum = int(query["max"][0])
                return httpx.Response(
                    200,
                    json=self.users[first : first + maximum],
                    request=httpx.Request(method, "https://kc" + path),
                )
            return await super()._keycloak_request(method, path, **kwargs)

    inventory = await KeycloakCutoverInventory.load(LargeAssignments())
    assert inventory.memberships["u1001"] == {"g2"}
    assert inventory.effective_roles["u1001"] == {"manager", "reader"}


def test_optional_export_subgroup_count_can_be_null():
    groups = KeycloakCutoverInventory._flatten_groups(
        [{"id": "g1", "name": "Root", "subGroupCount": None}]
    )
    assert groups["g1"]["path"] == "/Root"


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/users", "/roles/reader/users", "/clients/c/roles/r/users"])
async def test_user_pages_prefetch_at_most_eight_and_preserve_offset_order(path):
    class Pages:
        active = 0
        peak = 0
        calls = []

        async def _keycloak_request(self, method, endpoint):
            offset = int(parse_qs(urlsplit(endpoint).query)["first"][0])
            self.calls.append(offset)
            self.active += 1
            self.peak = max(self.peak, self.active)
            await asyncio.sleep(0)
            if offset == 2:
                await asyncio.sleep(0)
            self.active -= 1
            rows = [{"id": str(i)} for i in range(offset, min(offset + 2, 7))]
            return httpx.Response(
                200, json=rows, request=httpx.Request(method, "https://kc" + endpoint)
            )

    admin = Pages()
    inventory = KeycloakCutoverInventory(admin, page_size=2, concurrency=16)
    rows = await inventory._pages(path)
    assert [row["id"] for row in rows] == [str(i) for i in range(7)]
    assert admin.calls == list(range(0, 18, 2))
    assert admin.peak == 8 and admin.active == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_page", [[{"id": "first"}], [{"missing": "id"}], [None], {}])
async def test_prefetched_pages_reject_duplicate_ids_and_malformed_data(bad_page):
    class Pages:
        async def _keycloak_request(self, method, endpoint):
            offset = int(parse_qs(urlsplit(endpoint).query)["first"][0])
            rows = [{"id": "first"}] if offset == 0 else bad_page if offset == 1 else []
            return httpx.Response(
                200, json=rows, request=httpx.Request(method, "https://kc" + endpoint)
            )

    with pytest.raises(ValueError):
        await KeycloakCutoverInventory(Pages(), page_size=1)._pages("/users")


@pytest.mark.asyncio
async def test_prefetch_waits_for_all_requests_and_propagates_http_failure():
    class Pages:
        completed = []

        async def _keycloak_request(self, method, endpoint):
            offset = int(parse_qs(urlsplit(endpoint).query)["first"][0])
            await asyncio.sleep(0)
            self.completed.append(offset)
            return httpx.Response(
                503 if offset == 8 else 200,
                json=[{"id": "first"}] if offset == 0 else [],
                request=httpx.Request(method, "https://kc" + endpoint),
            )

    admin = Pages()
    with pytest.raises(httpx.HTTPStatusError):
        await KeycloakCutoverInventory(admin, page_size=1)._pages("/users")
    assert sorted(admin.completed) == list(range(9))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path,size,expected",
    [
        ("/groups/g/members", 1, [0, 1]),
        ("/roles", 1, [0, 1]),
        ("/clients/c/roles", 1, [0, 1]),
        ("/users", 2, [0]),
    ],
)
async def test_catalogs_remain_sequential_and_short_first_page_does_not_prefetch(
    path, size, expected
):
    class Pages:
        calls = []

        async def _keycloak_request(self, method, endpoint):
            offset = int(parse_qs(urlsplit(endpoint).query)["first"][0])
            self.calls.append(offset)
            return httpx.Response(
                200,
                json=[{"id": "first"}] if offset == 0 else [],
                request=httpx.Request(method, "https://kc" + endpoint),
            )

    admin = Pages()
    assert await KeycloakCutoverInventory(admin, page_size=size)._pages(path) == [{"id": "first"}]
    assert admin.calls == expected


@pytest.mark.asyncio
async def test_verified_client_service_accounts_are_excluded_from_application_assignments():
    class ServiceAccounts(InventoryAdmin):
        def __init__(self):
            super().__init__()
            self.export["clients"][0]["serviceAccountsEnabled"] = True

        async def _keycloak_request(self, method, path, **kwargs):
            parsed = urlsplit(path)
            if parsed.path in {
                "/clients/client-id/service-account-user",
                "/roles/reader/users",
                "/groups/g1/members",
            }:
                self.calls.append((method, path, {}))
                # The real account profile need not expose serviceAccountClientId.
                profile = {"id": "machine", "username": "service-account-service"}
                data = profile if parsed.path.endswith("service-account-user") else [profile]
                return httpx.Response(
                    200, json=data, request=httpx.Request(method, "https://kc" + path)
                )
            return await super()._keycloak_request(method, path, **kwargs)

    admin = ServiceAccounts()
    inventory = await KeycloakCutoverInventory.load(admin)
    assert "machine" not in inventory.users
    assert "machine" not in inventory.memberships
    assert "machine" not in inventory.effective_roles
    assert sum(path.endswith("service-account-user") for _, path, _ in admin.calls) == 1


@pytest.mark.asyncio
async def test_missing_ordinary_user_cannot_claim_service_account_status():
    class MissingUser(InventoryAdmin):
        async def _keycloak_request(self, method, path, **kwargs):
            if urlsplit(path).path == "/roles/reader/users":
                return httpx.Response(
                    200,
                    json=[
                        {
                            "id": "missing",
                            "username": "service-account-service",
                            "serviceAccountClientId": "service",
                        }
                    ],
                    request=httpx.Request(method, "https://kc" + path),
                )
            return await super()._keycloak_request(method, path, **kwargs)

    with pytest.raises(ValueError, match="Role assignment references absent user"):
        await KeycloakCutoverInventory.load(MissingUser())
