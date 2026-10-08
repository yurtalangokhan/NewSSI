from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_existing_assignment_import_adds_only_missing_active_grants():
    from src.service.keycloak_assignment_import import import_existing_assignments

    users = [{"id": "old", "keycloak_id": "kc", "role": "member"}, {"id": "new", "role": "member"}]
    source = {
        "users": users,
        "user_roles": [{"user_id": "old", "role_name": "member"}],
        "user_organizations": [
            {"user_id": "old", "organization_id": "g1", "is_active": True},
            {"user_id": "old", "organization_id": "g2", "is_active": False},
        ],
    }
    calls = []

    async def request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        if path.endswith("/groups"):
            return [{"id": "unrelated"}]
        if path.endswith("/realm/composite"):
            return [{"id": "custom", "name": "custom"}]

    client = SimpleNamespace(request=request)
    result = await import_existing_assignments(
        client,
        source,
        {
            "users": {"old": "kc", "new": "new-kc"},
            "organizations": {"g1": "active", "g2": "inactive"},
        },
        {"member": {"id": "member-id", "name": "member"}},
        apply=True,
    )
    assert result == {"memberships_added": 1, "roles_added": 1}
    assert [(method, path) for method, path, _ in calls if method != "GET"] == [
        ("PUT", "/users/kc/groups/active"),
        ("POST", "/users/kc/role-mappings/realm"),
    ]
    assert calls[-1][2]["json"] == [{"id": "member-id", "name": "member"}]
    assert not any("new-kc" in path for _, path, _ in calls)


@pytest.mark.asyncio
async def test_existing_assignment_import_preserves_inherited_roles_and_dry_run():
    from src.service.keycloak_assignment_import import import_existing_assignments

    client = SimpleNamespace(request=AsyncMock(side_effect=[[], [{"name": "member", "id": "r"}]]))
    source = {
        "users": [{"id": "old", "keycloak_id": "kc", "role": "member"}],
        "user_organizations": [{"user_id": "old", "organization_id": "g"}],
    }
    result = await import_existing_assignments(
        client,
        source,
        {"users": {"old": "kc"}, "organizations": {"g": "group"}},
        {"member": {"id": "r", "name": "member"}},
    )
    assert result == {"memberships_added": 1, "roles_added": 0}
    assert all(call.args[0] == "GET" for call in client.request.call_args_list)


@pytest.mark.asyncio
async def test_existing_assignment_import_preflights_missing_mapping_before_writes():
    from src.service.keycloak_assignment_import import import_existing_assignments

    client = SimpleNamespace(request=AsyncMock())
    source = {
        "users": [{"id": "old", "keycloak_id": "kc", "role": "member"}],
        "user_organizations": [{"user_id": "old", "organization_id": "g"}],
    }
    with pytest.raises(ValueError, match="organization"):
        await import_existing_assignments(
            client,
            source,
            {"users": {"old": "kc"}},
            {"member": {"id": "r", "name": "member"}},
            apply=True,
        )
    client.request.assert_not_called()


@pytest.mark.asyncio
async def test_existing_assignment_import_retry_has_no_writes_when_grants_are_present():
    from src.service.keycloak_assignment_import import import_existing_assignments

    client = SimpleNamespace(
        request=AsyncMock(
            side_effect=[
                [{"id": "group"}, {"id": "other"}],
                [{"name": "member", "id": "r"}, {"name": "custom", "id": "x"}],
            ]
        )
    )
    source = {
        "users": [{"id": "old", "keycloak_id": "kc", "role": "member"}],
        "user_organizations": [{"user_id": "old", "organization_id": "g"}],
    }
    assert await import_existing_assignments(
        client,
        source,
        {"users": {"old": "kc"}, "organizations": {"g": "group"}},
        {"member": {"id": "r", "name": "member"}},
        apply=True,
    ) == {"memberships_added": 0, "roles_added": 0}
    assert all(call.args[0] == "GET" for call in client.request.call_args_list)
