from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.repository.user_repository import UserRepository
from src.service.user_service import UserService


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
        list_paginated=AsyncMock(return_value=([_user()], 1)),
        get_by_keycloak_id=AsyncMock(return_value=None),
        upsert_by_keycloak_id=AsyncMock(return_value=_user()),
    )
    service.settings_repo = SimpleNamespace(ensure_defaults=AsyncMock())
    return service


@pytest.mark.asyncio
async def test_list_users_hides_external_keycloak_users_when_external_keycloak_is_disabled():
    service = _service(external_keycloak=False)

    users, total = await service.list_users()

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
async def test_create_user_sets_keycloak_password_credential():
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
    )
    service.role_repo = SimpleNamespace(exists=AsyncMock(return_value=True))
    service.settings_repo = SimpleNamespace(ensure_defaults=AsyncMock())

    user = await service.create_user(
        email="USER@example.com",
        username="newuser",
        first_name="New",
        last_name="User",
        role="enduser",
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


@pytest.mark.asyncio
async def test_user_repository_falls_back_when_external_keycloak_flag_column_is_missing(
    monkeypatch,
):
    repo = UserRepository()
    statements = []

    class CountResult:
        def scalar_one(self):
            return 0

    class RowsResult:
        class Scalars:
            def all(self):
                return []

        def scalars(self):
            return self.Scalars()

    class FakeSession:
        async def execute(self, statement):
            statements.append(statement)
            return CountResult() if len(statements) == 1 else RowsResult()

        async def commit(self):
            return None

        async def rollback(self):
            return None

    class FakeSessionContext:
        async def __aenter__(self):
            return FakeSession()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(repo, "_session", lambda: FakeSessionContext())
    monkeypatch.setattr(
        repo, "_external_keycloak_user_column_exists", AsyncMock(return_value=False)
    )

    users, total = await repo.list_paginated(include_external_keycloak_users=False)

    assert users == []
    assert total == 0
    compiled_count_query = str(statements[0])
    assert "users.keycloak_id IS NULL" in compiled_count_query
    assert "is_external_keycloak_user" not in compiled_count_query
