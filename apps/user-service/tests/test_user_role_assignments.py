import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.service.user_service import UserService


def _user(**overrides):
    defaults = {
        "id": uuid.uuid4(),
        "email": "user@example.com",
        "keycloak_id": "kc-user-id",
        "role": "enduser",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.mark.asyncio
async def test_assign_roles_appends_roles_and_mirrors_primary_role():
    user_id = uuid.uuid4()
    user = _user(id=user_id, role="enduser")
    updated = _user(id=user_id, role="auditor")
    service = UserService()
    service.user_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=user), update=AsyncMock(return_value=updated)
    )
    service.role_repo = SimpleNamespace(
        get_by_names=AsyncMock(return_value=[SimpleNamespace(name="auditor")])
    )
    service.user_role_repo = SimpleNamespace(
        assign_roles=AsyncMock(),
        list_user_roles=AsyncMock(return_value=[{"name": "auditor", "is_primary": True}]),
    )
    service.permission_resolver = SimpleNamespace(invalidate_user=AsyncMock())
    service.keycloak = SimpleNamespace(
        is_enabled=lambda: True,
        set_realm_role=AsyncMock(return_value=True),
        logout_user_sessions=AsyncMock(return_value=True),
    )

    result = await service.assign_roles(user_id, ["auditor"], primary_role="auditor")

    assert result == {"roles": [{"name": "auditor", "is_primary": True}]}
    service.user_role_repo.assign_roles.assert_awaited_once_with(
        user_id,
        ["auditor"],
        primary_role="auditor",
    )
    service.user_repo.update.assert_awaited_once_with(user_id, role="auditor")
    service.keycloak.set_realm_role.assert_awaited_once_with("kc-user-id", "auditor")
    service.permission_resolver.invalidate_user.assert_awaited_once_with(user_id)


@pytest.mark.asyncio
async def test_remove_role_rejects_removing_last_role():
    user_id = uuid.uuid4()
    service = UserService()
    service.user_repo = SimpleNamespace(get_by_id=AsyncMock(return_value=_user(id=user_id)))
    service.user_role_repo = SimpleNamespace(
        list_user_roles=AsyncMock(return_value=[{"name": "enduser", "is_primary": True}])
    )

    with pytest.raises(ValueError, match="last role"):
        await service.remove_role(user_id, "enduser")
