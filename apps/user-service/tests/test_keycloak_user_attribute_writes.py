"""Writing application attributes never erases a user's name or email.

Keycloak 26 replaces the profile on ``PUT /users/{id}``, so an attributes-only
body clears email, first name and last name (verified against the realm).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.repository.user_organization_repository import UserOrganizationRepository
from src.repository.user_role_repository import UserRoleRepository
from tests.test_keycloak_group_cutover import snapshot
from tests.test_keycloak_organizations import ROOT, USER, Admin

PROFILE = {"email": "alice@example.test", "firstName": "Alice", "lastName": "Öztürk"}


def profile_of(admin):
    stored = admin.users[str(USER)]
    return {field: stored.get(field) for field in PROFILE}


@pytest.mark.asyncio
async def test_primary_role_marker_keeps_the_profile(monkeypatch):
    admin = Admin()
    monkeypatch.setattr("src.service.keycloak_service.get_keycloak_service", lambda: admin)
    repo = UserRoleRepository()
    repo.list_user_roles = AsyncMock(return_value=[{"name": "auditor"}])

    assert await repo.set_primary_role(USER, "auditor") is True

    assert admin.users[str(USER)]["attributes"]["agentic.primary_role"] == ["auditor"]
    assert profile_of(admin) == PROFILE


@pytest.mark.asyncio
async def test_organization_membership_metadata_keeps_the_profile():
    admin = Admin()

    await UserOrganizationRepository(admin).create(USER, ROOT, is_primary=True)

    assert admin.users[str(USER)]["attributes"]["agenticai.primary_organization"] == [str(ROOT)]
    assert profile_of(admin) == PROFILE


@pytest.mark.asyncio
async def test_group_metadata_cutover_keeps_the_profile():
    from src.service.keycloak_group_cutover import reconcile_group_metadata
    from tests.test_keycloak_organizations import CHILD

    admin = Admin()
    mappings = {"users": {str(USER): str(USER)}, "organizations": {str(CHILD): str(CHILD)}}

    await reconcile_group_metadata(admin, snapshot(), mappings, apply=True)

    assert admin.users[str(USER)]["attributes"]["agentic.team_name"] == ["Platform"]
    assert profile_of(admin) == PROFILE


@pytest.mark.asyncio
async def test_role_metadata_cutover_sends_the_full_representation():
    from src.service.keycloak_role_cutover import reconcile_role_metadata

    user = {"id": "kc-user", "username": "alice", **PROFILE, "attributes": {"keep": ["x"]}}
    client = SimpleNamespace(
        request=AsyncMock(side_effect=[user, [{"id": "role", "name": "auditor"}], None])
    )
    snapshot_rows = {
        "users": [{"id": "legacy-user", "role": "enduser"}],
        "user_roles": [{"user_id": "legacy-user", "role_name": "auditor", "is_primary": True}],
    }

    await reconcile_role_metadata(
        client, snapshot_rows, mappings={"users": {"legacy-user": "kc-user"}}, apply=True
    )

    body = client.request.call_args.kwargs["json"]
    assert {field: body.get(field) for field in PROFILE} == PROFILE
    assert body["attributes"] == {"keep": ["x"], "agentic.primary_role": ["auditor"]}
