import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.repository.user_repository import UserRepository
from src.service.user_service import UserService


@pytest.mark.asyncio
async def test_delete_user_projects_resource_permission_cleanup() -> None:
    async def project(mutation):
        return await mutation()

    service = UserService()
    service.user_repo = MagicMock(delete=AsyncMock(return_value=True))
    service.settings_repo = MagicMock(delete=AsyncMock())
    service.permission_resolver = MagicMock(invalidate_user=AsyncMock())
    user_id = uuid.uuid4()
    permission_cleanup = AsyncMock(return_value=2)

    with (
        patch("src.repository.ApiKeyRepository") as api_keys,
        patch("src.repository.UserMemoryRepository") as memories,
        patch(
            "src.repository.resource_permission_repository.ResourcePermissionRepository"
        ) as permissions,
        patch(
            "src.repository.keycloak_resource_authorization.project_resource_permission_mutation",
            AsyncMock(side_effect=project),
        ) as projection,
    ):
        api_keys.return_value.delete_by_user = AsyncMock()
        memories.return_value.delete_all = AsyncMock()
        permissions.return_value.delete_user_permissions = permission_cleanup
        assert await service.delete_user(user_id) is True

    projection.assert_awaited_once()
    permission_cleanup.assert_awaited_once_with(user_id)


def _user(**overrides):
    defaults = {
        "id": "00000000-0000-0000-0000-000000000001",
        "email": "user@example.com",
        "username": "user",
        "first_name": "Test",
        "last_name": "User",
        "is_active": True,
        "is_verified": True,
        "role": "enduser",
        "invited": False,
        "password_configured": False,
        "is_external_keycloak_user": False,
        "team_name": None,
        "keycloak_id": "kc-123",
        "created_at": datetime(2026, 6, 23),
        "updated_at": datetime(2026, 6, 23),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _service(external_keycloak: bool) -> UserService:
    service = UserService()
    service.keycloak = SimpleNamespace(
        is_external_keycloak=lambda: external_keycloak,
        get_external_keycloak_alias=lambda: "external-keycloak",
        user_has_federated_identity=AsyncMock(return_value=external_keycloak),
    )
    service.user_repo = SimpleNamespace(
        list_paginated=AsyncMock(return_value=([_user()], 1, True)),
        get_by_id=AsyncMock(return_value=None),
        upsert_by_keycloak_id=AsyncMock(return_value=_user()),
    )
    service.settings_repo = SimpleNamespace(ensure_defaults=AsyncMock())
    return service


@pytest.mark.asyncio
async def test_list_users_hides_external_keycloak_users_when_external_keycloak_is_disabled():
    service = _service(external_keycloak=False)

    users, total, _ = await service.list_users()

    assert total == 1
    assert users[0]["is_external_keycloak_user"] is False
    service.user_repo.list_paginated.assert_awaited_once_with(
        0,
        20,
        None,
        None,
        None,
        None,
        None,
        False,
    )


@pytest.mark.asyncio
async def test_list_users_includes_external_keycloak_users_when_external_keycloak_is_enabled():
    service = _service(external_keycloak=True)

    await service.list_users()

    service.user_repo.list_paginated.assert_awaited_once_with(
        0,
        20,
        None,
        None,
        None,
        None,
        None,
        True,
    )


@pytest.mark.asyncio
async def test_upsert_user_from_keycloak_marks_users_from_external_keycloak():
    service = _service(external_keycloak=True)

    await service.upsert_user_from_keycloak(
        keycloak_id="kc-123",
        email="user@example.com",
        first_name="Test",
        last_name="User",
        username="user",
    )

    service.user_repo.upsert_by_keycloak_id.assert_awaited_once_with(
        keycloak_id="kc-123",
        email="user@example.com",
        first_name="Test",
        last_name="User",
        username="user",
        is_active=True,
        is_verified=True,
        is_external_keycloak_user=True,
        role="enduser",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("role_id", [None, "953ea848-0d1d-4c65-87b2-565c29b9f5df"])
async def test_create_user_sets_keycloak_password_credential(role_id):
    service = UserService()
    service.keycloak = SimpleNamespace(
        is_enabled=lambda: True,
        get_user_by_email=AsyncMock(return_value=None),
        create_user=AsyncMock(return_value="kc-123"),
        delete_user=AsyncMock(),
        set_realm_role=AsyncMock(return_value=True),
    )
    service.user_repo = SimpleNamespace(
        exists_by_email=AsyncMock(return_value=False),
        create=AsyncMock(return_value=_user(password_configured=True)),
        get_by_id=AsyncMock(return_value=_user(password_configured=True)),
    )
    service.user_role_repo = SimpleNamespace(replace_roles=AsyncMock())
    service.role_repo = SimpleNamespace(
        get_by_ids=AsyncMock(
            return_value=[
                SimpleNamespace(id="953ea848-0d1d-4c65-87b2-565c29b9f5df", name="enduser")
            ]
        ),
    )
    service.settings_repo = SimpleNamespace(ensure_defaults=AsyncMock())

    user = await service.create_user(
        email="USER@example.com",
        username="newuser",
        first_name="New",
        last_name="User",
        role_id=role_id,
        password="securepassword123",
    )

    service.keycloak.create_user.assert_awaited_once_with(
        {
            "email": "user@example.com",
            "username": "newuser",
            "firstName": "New",
            "lastName": "User",
            "enabled": True,
            "emailVerified": True,
            "requiredActions": [],
            "credentials": [
                {
                    "type": "password",
                    "value": "securepassword123",
                    "temporary": False,
                }
            ],
        }
    )
    service.user_repo.create.assert_awaited_once()
    assert service.user_repo.create.await_args.kwargs["password_configured"] is True
    assert user["password_configured"] is True

    service.user_role_repo.replace_roles.assert_awaited_once_with(
        _user().id, ["enduser"], primary_role="enduser"
    )


@pytest.mark.asyncio
async def test_user_repository_filters_external_identities_without_local_schema():
    repo = UserRepository(keycloak=AsyncMock())

    async def profiles(path, **filters):
        yield {
            "id": str(uuid.uuid4()),
            "attributes": {"agentic.is_external_keycloak_user": ["true"]},
        }
        yield {"id": str(uuid.uuid4())}

    repo._pages = profiles
    repo._roles = AsyncMock(return_value=[])
    repo._group_paths = AsyncMock(return_value=[])
    users, total, _ = await repo.list_paginated(include_external_keycloak_users=False)
    assert total == 1
    assert users[0].is_external_keycloak_user is False
