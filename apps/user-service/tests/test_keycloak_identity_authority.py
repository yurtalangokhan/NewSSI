import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.service.user_service import UserService


def service():
    instance = UserService.__new__(UserService)
    instance.user_repo = AsyncMock()
    instance.user_role_repo = AsyncMock()
    instance.role_repo = AsyncMock()
    instance.keycloak = AsyncMock()
    instance.keycloak.is_enabled = lambda: True
    instance.permission_resolver = AsyncMock()
    return instance


@pytest.mark.asyncio
async def test_current_user_read_does_not_reassign_roles():
    svc = service()
    user = SimpleNamespace(id=uuid.uuid4(), keycloak_id="subject", role="custom")
    svc.user_repo.get_by_id.return_value = user
    svc._user_to_app_dict = AsyncMock(return_value={"id": str(user.id)})
    await svc.get_current_user(str(user.id))
    svc.user_repo.update.assert_not_awaited()
    svc.user_role_repo.replace_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_primary_role_selection_does_not_replace_all_assignments():
    svc = service()
    user = SimpleNamespace(id=uuid.uuid4(), keycloak_id="subject", role="custom")
    await svc._mirror_primary_role(user, "enduser")
    svc.keycloak.set_realm_role.assert_not_awaited()
    svc.user_repo.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_role_read_does_not_grant_default_role():
    svc = service()
    svc.user_role_repo.list_user_roles.return_value = []
    await svc.list_user_roles(uuid.uuid4())
    svc.user_role_repo.assign_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_target_authorization_checks_allowed_boolean():
    from src.core.exceptions import ForbiddenError

    svc = service()
    actor, target = uuid.uuid4(), uuid.uuid4()
    svc.resolve_target_user_id = AsyncMock(return_value=target)
    svc.user_repo.get_by_id.return_value = SimpleNamespace(id=actor)
    svc.user_has_permission = AsyncMock(return_value={"allowed": False})
    with pytest.raises(ForbiddenError):
        await svc.authorize_target_user_id(str(target), str(actor))


@pytest.mark.asyncio
async def test_user_role_assignment_accepts_keycloak_role_ids():
    svc = service()
    user_id, role_id = uuid.uuid4(), str(uuid.uuid4())
    svc.user_repo.get_by_id.return_value = SimpleNamespace(
        id=user_id, keycloak_id=str(user_id), role="enduser"
    )
    svc.role_repo.get_by_ids.return_value = [SimpleNamespace(id=role_id, name="reviewer")]
    svc.user_role_repo.list_user_roles.return_value = [
        {"id": role_id, "name": "reviewer", "is_primary": True}
    ]
    await svc.assign_roles(user_id, [role_id], primary_role_id=role_id)
    svc.user_role_repo.assign_roles.assert_awaited_once_with(
        user_id, ["reviewer"], primary_role="reviewer"
    )
