import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.main import _ensure_default_admin


@pytest.mark.asyncio
async def test_startup_bootstrap_uses_db_default_admin_role_without_service_class():
    admin_role = SimpleNamespace(name="system-admin", description="System administrator")
    role_repo = SimpleNamespace(get_default_admin_role=AsyncMock(return_value=admin_role))
    settings = SimpleNamespace(
        KEYCLOAK_ADMIN_EMAIL="admin@example.com",
        KEYCLOAK_BOOTSTRAP_ADMIN_EMAIL=None,
        KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD="secret",
    )
    keycloak = SimpleNamespace(
        is_enabled=lambda: True,
        get_user_by_email=AsyncMock(return_value=None),
        create_user=AsyncMock(return_value="kc-admin-id"),
        update_user=AsyncMock(return_value=True),
        set_password=AsyncMock(return_value=True),
        set_realm_role=AsyncMock(return_value=True),
    )
    user_repo = SimpleNamespace(
        upsert_by_keycloak_id=AsyncMock(
            return_value=SimpleNamespace(id=uuid.uuid4(), email="admin@example.com")
        )
    )
    settings_repo = SimpleNamespace(ensure_defaults=AsyncMock())

    result = await _ensure_default_admin(
        settings=settings,
        keycloak=keycloak,
        role_repo=role_repo,
        user_repo=user_repo,
        settings_repo=settings_repo,
    )

    assert result == {"status": "created", "email": "admin@example.com", "role": "system-admin"}
    keycloak.create_user.assert_awaited_once()
    keycloak.set_realm_role.assert_awaited_once_with("kc-admin-id", "system-admin")
    user_repo.upsert_by_keycloak_id.assert_awaited_once_with(
        "kc-admin-id",
        email="admin@example.com",
        username="admin",
        first_name="Default",
        last_name="Admin",
        role="system-admin",
        is_active=True,
        is_verified=True,
        is_external_keycloak_user=False,
    )


@pytest.mark.asyncio
async def test_startup_bootstrap_fails_when_no_default_admin_role_exists():
    role_repo = SimpleNamespace(get_default_admin_role=AsyncMock(return_value=None))
    settings = SimpleNamespace(
        KEYCLOAK_ADMIN_EMAIL="admin@example.com",
        KEYCLOAK_BOOTSTRAP_ADMIN_EMAIL=None,
        KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD="secret",
    )
    keycloak = SimpleNamespace(is_enabled=lambda: True)

    with pytest.raises(ValueError, match="default admin role"):
        await _ensure_default_admin(
            settings=settings,
            keycloak=keycloak,
            role_repo=role_repo,
            user_repo=SimpleNamespace(),
            settings_repo=SimpleNamespace(),
        )
