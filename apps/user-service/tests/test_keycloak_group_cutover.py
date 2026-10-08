"""Metadata cutover validates all changes before writing authoritative identities."""

import json
from uuid import uuid4

import pytest

from src.service.keycloak_group_cutover import reconcile_group_metadata
from tests.test_keycloak_organizations import CHILD, USER, Admin


def snapshot():
    return {
        "organizations": [{"id": CHILD, "code": "DEPT", "metadata_json": {"color": "blue"}}],
        "users": [{"id": USER, "team_name": "Platform", "invited": True}],
        "user_organizations": [
            {
                "id": uuid4(),
                "user_id": USER,
                "organization_id": CHILD,
                "is_active": True,
                "is_primary": True,
            }
        ],
    }


@pytest.mark.asyncio
async def test_reconciles_missing_metadata_without_altering_groups_or_memberships():
    admin = Admin()
    data = snapshot()
    mappings = {"users": {str(USER): str(USER)}, "organizations": {str(CHILD): str(CHILD)}}
    assert await reconcile_group_metadata(admin, data, mappings, apply=False) == 2
    assert all(method == "GET" for method, _, _ in admin.calls)
    assert await reconcile_group_metadata(admin, data, mappings, apply=True) == 2
    assert admin.groups[str(CHILD)]["name"] == "Child"
    assert admin.members[str(USER)] == {str(CHILD)}
    attrs = admin.users[str(USER)]["attributes"]
    assert json.loads(attrs["agenticai.memberships"][0])[str(CHILD)]["id"] == str(
        data["user_organizations"][0]["id"]
    )
    assert attrs["agenticai.primary_organization"] == [str(CHILD)]
    assert attrs["agentic.team_name"] == ["Platform"]
    assert await reconcile_group_metadata(admin, data, mappings, apply=True) == 0


@pytest.mark.asyncio
async def test_conflict_prevents_every_write():
    admin = Admin()
    admin.users[str(USER)]["attributes"]["agentic.team_name"] = ["Existing team"]
    mappings = {"users": {str(USER): str(USER)}, "organizations": {str(CHILD): str(CHILD)}}
    with pytest.raises(ValueError, match="metadata conflict"):
        await reconcile_group_metadata(admin, snapshot(), mappings, apply=True)
    assert all(method == "GET" for method, _, _ in admin.calls)


@pytest.mark.asyncio
async def test_absent_authoritative_membership_is_not_recreated():
    admin = Admin()
    admin.members[str(USER)].clear()
    data = snapshot()
    mappings = {"users": {str(USER): str(USER)}, "organizations": {str(CHILD): str(CHILD)}}
    with pytest.raises(ValueError, match="membership"):
        await reconcile_group_metadata(admin, data, mappings, apply=True)
    assert all(method == "GET" for method, _, _ in admin.calls)
