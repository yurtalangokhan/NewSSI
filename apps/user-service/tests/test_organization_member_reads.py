"""Selected organization reads derive membership from its member endpoint."""

import json
import uuid
from unittest.mock import AsyncMock

import httpx
import pytest

from src.repository.user_organization_repository import (
    MEMBERSHIPS,
    PRIMARY,
    UserOrganizationRepository,
)


@pytest.fixture
def members():
    org_id, active_id, inactive_id, saved_id = [str(uuid.UUID(int=i)) for i in range(1, 5)]
    org = {"id": uuid.UUID(org_id), "name": "Team", "code": "TEAM", "level": 1, "is_active": True}
    active = {
        "id": active_id,
        "username": "active",
        "attributes": {
            PRIMARY: [org_id],
            MEMBERSHIPS: [
                json.dumps({org_id: {"id": saved_id, "joined_at": "2021", "is_active": False}})
            ],
        },
    }
    inactive = {
        "id": inactive_id,
        "username": "inactive",
        "attributes": {
            PRIMARY: [org_id],
            MEMBERSHIPS: [json.dumps({org_id: {"joined_at": "2020", "is_active": True}})],
        },
    }
    keycloak = AsyncMock()
    repo = UserOrganizationRepository(keycloak)
    repo.organizations.get_by_id = AsyncMock(return_value=org)
    repo.client.pages = AsyncMock(return_value=[active])
    repo._memberships = AsyncMock(side_effect=AssertionError("Per-user group lookup"))
    return repo, keycloak, org, active, inactive, saved_id


async def test_active_member_read_uses_group_members_as_authority(members):
    repo, _, org, active, _, saved_id = members
    rows = await repo.get_organization_users(org["id"])
    assert len(rows) == 1
    assert rows[0]["id"] == uuid.UUID(saved_id)
    assert rows[0]["user_id"] == uuid.UUID(active["id"])
    assert rows[0]["is_primary"] is True and rows[0]["is_active"] is True
    repo.client.pages.assert_awaited_once_with(f"/groups/{org['id']}/members")
    assert await repo.count_organization_users(org["id"]) == 1


async def test_inactive_read_combines_profile_metadata_and_active_member_ids(members):
    repo, keycloak, org, active, inactive, _ = members

    async def request(method, path, **kwargs):
        assert path == "/users"
        assert kwargs["params"]["max"] == 1000
        return httpx.Response(
            200,
            json=[active, inactive, {"id": str(uuid.UUID(int=10))}],
            request=httpx.Request(method, "https://kc.invalid/users"),
        )

    keycloak._keycloak_request.side_effect = request
    rows = await repo.get_organization_users(org["id"], include_inactive=True)
    assert [str(row["user_id"]) for row in rows] == [inactive["id"], active["id"]]
    assert rows[0]["is_active"] is False and rows[0]["is_primary"] is False
    assert rows[1]["is_active"] is True and rows[1]["is_primary"] is True
    repo.client.pages.assert_awaited_once_with(f"/groups/{org['id']}/members")


async def test_inactive_organization_has_no_active_members(members):
    repo, _, org, _, _, _ = members
    org["is_active"] = False
    assert await repo.get_organization_users(org["id"]) == []
    repo.client.pages.assert_not_awaited()
