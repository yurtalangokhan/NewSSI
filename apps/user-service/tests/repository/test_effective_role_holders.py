"""Finding one role's holders reads only that role's ancestors, never the whole directory."""

import uuid

import httpx
import pytest

from src.repository.user_repository import UserRepository
from src.repository.user_role_repository import UserRoleRepository

AUDITOR, MANAGER, ENDUSER, DEFAULT = "r-auditor", "r-manager", "r-enduser", "r-default"
U_DIRECT, U_COMPOSITE, U_GROUP, U_SUBGROUP, U_ENDUSER = (str(uuid.UUID(int=i)) for i in range(1, 6))


class Directory:
    """Keycloak admin reads for a realm where everyone holds enduser via default roles."""

    def __init__(self):
        self.paths = []
        self.data = {
            "/roles": [
                {"id": AUDITOR, "name": "auditor", "composite": False},
                {"id": MANAGER, "name": "manager", "composite": True},
                {"id": ENDUSER, "name": "enduser", "composite": False},
                {"id": DEFAULT, "name": "default-roles-agenticai", "composite": True},
            ],
            "/clients": [],
            f"/roles-by-id/{MANAGER}/composites": [{"id": AUDITOR, "name": "auditor"}],
            f"/roles-by-id/{DEFAULT}/composites": [{"id": ENDUSER, "name": "enduser"}],
            "/roles/auditor/users": [{"id": U_DIRECT}],
            "/roles/auditor/groups": [{"id": "g-auditors"}],
            "/roles/manager/users": [{"id": U_COMPOSITE}],
            "/roles/manager/groups": [],
            "/groups/g-auditors/children": [{"id": "g-auditors-eu"}],
            "/groups/g-auditors-eu/children": [],
            "/groups/g-auditors/members": [{"id": U_GROUP}],
            "/groups/g-auditors-eu/members": [{"id": U_SUBGROUP}],
            "/roles/enduser/users": [{"id": U_ENDUSER}],
            "/roles/default-roles-agenticai/users": [{"id": U_ENDUSER}],
        }

    def get_realm(self):
        return "agenticai"

    async def _keycloak_request(self, method, path, params=None, **kwargs):
        self.paths.append(path)
        rows = self.data[path]
        first = int((params or {}).get("first", 0))
        size = int((params or {}).get("max", len(rows) or 1))
        request = httpx.Request(method, f"https://kc{path}")
        return httpx.Response(200, json=rows[first : first + size], request=request)


@pytest.mark.asyncio
async def test_holders_include_direct_composite_group_and_subgroup_assignments():
    directory = Directory()

    holders = await UserRepository(directory).effective_role_holders("auditor")

    assert holders == {U_DIRECT, U_COMPOSITE, U_GROUP, U_SUBGROUP}


@pytest.mark.asyncio
async def test_holders_never_list_members_of_unrelated_roles():
    directory = Directory()

    await UserRepository(directory).effective_role_holders("auditor")

    assert "/roles/enduser/users" not in directory.paths
    assert "/roles/default-roles-agenticai/users" not in directory.paths


@pytest.mark.asyncio
async def test_unknown_role_has_no_holders():
    assert await UserRepository(Directory()).effective_role_holders("ghost") == set()


@pytest.mark.asyncio
async def test_session_revocation_targets_are_the_effective_holders(monkeypatch):
    directory = Directory()
    monkeypatch.setattr(
        "src.repository.user_repository.UserRepository.__init__",
        lambda self, keycloak=None: setattr(self, "keycloak", directory),
    )

    ids = await UserRoleRepository().list_user_ids_by_role("auditor")

    assert ids == sorted(uuid.UUID(i) for i in (U_DIRECT, U_COMPOSITE, U_GROUP, U_SUBGROUP))
    assert "/roles/enduser/users" not in directory.paths
