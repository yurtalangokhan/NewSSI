import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from error_contract import ConflictError

from tests.error_support import raises_localized
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
async def test_assign_roles_preserves_existing_grants_and_delegates_primary_metadata():
    user_id = uuid.uuid4()
    user = _user(id=user_id, role="enduser")
    updated = _user(id=user_id, role="auditor")
    service = UserService()
    service.user_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=user), update=AsyncMock(return_value=updated)
    )
    service.role_repo = SimpleNamespace(
        get_by_ids=AsyncMock(return_value=[SimpleNamespace(id="auditor-id", name="auditor")])
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

    result = await service.assign_roles(user_id, ["auditor-id"], primary_role_id="auditor-id")

    assert result == {"roles": [{"name": "auditor", "is_primary": True}]}
    service.user_role_repo.assign_roles.assert_awaited_once_with(
        user_id,
        ["auditor"],
        primary_role="auditor",
    )
    service.user_repo.update.assert_not_called()
    service.keycloak.set_realm_role.assert_not_called()
    service.keycloak.logout_user_sessions.assert_awaited_once_with("kc-user-id")
    service.permission_resolver.invalidate_user.assert_awaited_once_with(user_id)


@pytest.mark.asyncio
async def test_remove_role_rejects_removing_last_role():
    user_id = uuid.uuid4()
    service = UserService()
    service.user_repo = SimpleNamespace(get_by_id=AsyncMock(return_value=_user(id=user_id)))
    service.user_role_repo = SimpleNamespace(
        list_user_roles=AsyncMock(return_value=[{"name": "enduser", "is_primary": True}])
    )

    with raises_localized(ConflictError, "last role"):
        await service.remove_role(user_id, "enduser")


@pytest.mark.asyncio
@pytest.mark.parametrize("read_only", [False, True])
@pytest.mark.parametrize("secondary", [False, True])
async def test_reads_preserve_assignments_and_explicit_updates_replace_them(read_only, secondary):
    user = _user(role="system-admin")
    service = UserService()
    service.user_repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=user),
        update=AsyncMock(return_value=_user(id=user.id, role="enterprise-admin")),
    )
    service.role_repo = SimpleNamespace(
        get_by_ids=AsyncMock(return_value=[SimpleNamespace(id="ea-id", name="enterprise-admin")])
    )
    service.user_role_repo = SimpleNamespace(
        replace_roles=AsyncMock(),
        list_user_roles=AsyncMock(
            return_value=[{"name": "system-admin", "is_primary": True}]
            + ([{"name": "auditor", "is_primary": False}] if secondary else [])
        ),
    )
    service.permission_resolver = SimpleNamespace(invalidate_user=AsyncMock())
    service.keycloak = SimpleNamespace(
        is_enabled=lambda: True, logout_user_sessions=AsyncMock(return_value=True)
    )
    service._user_to_app_dict = AsyncMock(return_value={})
    service._user_to_dict = lambda user: {}
    if read_only:
        await service.get_current_user(str(user.id))
        service.user_role_repo.replace_roles.assert_not_called()
        service.user_repo.update.assert_not_called()
        service.permission_resolver.invalidate_user.assert_not_called()
        service.keycloak.logout_user_sessions.assert_not_called()
    else:
        await service.replace_role(user.id, "ea-id")
        service.user_role_repo.replace_roles.assert_awaited_once_with(
            user.id, ["enterprise-admin"], primary_role="enterprise-admin"
        )
        service.user_repo.update.assert_not_called()
        service.permission_resolver.invalidate_user.assert_awaited_once_with(user.id)
        service.keycloak.logout_user_sessions.assert_awaited_once_with("kc-user-id")
