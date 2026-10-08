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
        get_user_by_username=AsyncMock(return_value=None),
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
async def test_startup_does_not_reset_password_of_an_existing_admin():
    """KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD provisions the admin once, at creation.

    Re-applying it to an already-existing admin on every subsequent startup
    means anyone who knows that value (an env default, a leaked .env, a
    value the operator forgot to change) can take the account back over at
    any time simply by causing a restart -- even long after the real admin
    changed their password out of band. Once the account exists, startup
    must leave its password alone.
    """
    admin_role = SimpleNamespace(name="system-admin", description="System administrator")
    role_repo = SimpleNamespace(get_default_admin_role=AsyncMock(return_value=admin_role))
    settings = SimpleNamespace(
        KEYCLOAK_ADMIN_EMAIL="admin@example.com",
        KEYCLOAK_BOOTSTRAP_ADMIN_EMAIL=None,
        KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD="change-me",
    )
    existing_user = {"id": "kc-admin-id", "email": "admin@example.com", "username": "admin"}
    keycloak = SimpleNamespace(
        is_enabled=lambda: True,
        get_user_by_email=AsyncMock(return_value=existing_user),
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

    assert result["status"] == "exists"
    keycloak.set_password.assert_not_awaited()


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


@pytest.mark.asyncio
async def test_existing_admin_identity_is_never_overwritten_on_startup():
    keycloak = SimpleNamespace(
        is_enabled=lambda: True,
        get_user_by_email=AsyncMock(return_value={"id": str(uuid.uuid4())}),
        update_user=AsyncMock(),
        set_password=AsyncMock(),
        set_realm_role=AsyncMock(),
    )
    await _ensure_default_admin(
        settings=SimpleNamespace(
            KEYCLOAK_ADMIN_EMAIL="admin@example.com",
            KEYCLOAK_BOOTSTRAP_ADMIN_EMAIL=None,
            KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD="old-password",
        ),
        keycloak=keycloak,
        role_repo=SimpleNamespace(
            get_default_admin_role=AsyncMock(return_value=SimpleNamespace(name="system-admin"))
        ),
        user_repo=SimpleNamespace(
            upsert_by_keycloak_id=AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4()))
        ),
        settings_repo=SimpleNamespace(ensure_defaults=AsyncMock()),
    )
    keycloak.update_user.assert_not_awaited()
    keycloak.set_password.assert_not_awaited()
    keycloak.set_realm_role.assert_not_awaited()


@pytest.mark.asyncio
async def test_startup_finds_existing_admin_by_username_when_keycloak_record_has_no_email():
    """A Keycloak account can exist with no email set -- for example one the
    identity cutover import reused rather than overwrote (see
    keycloak_identity_import.py's reuse-matching path). Email-only lookup
    then finds nothing and startup tries to create a duplicate, which
    Keycloak rejects with a 409 on the already-taken username. Keycloak
    itself enforces username uniqueness regardless of email, so the
    existence check must fall back to a username lookup too.
    """
    existing_user = {"id": "kc-admin-id", "username": "admin"}
    role_repo = SimpleNamespace(
        get_default_admin_role=AsyncMock(return_value=SimpleNamespace(name="system-admin"))
    )
    settings = SimpleNamespace(
        KEYCLOAK_ADMIN_EMAIL="admin@agenticai.local",
        KEYCLOAK_BOOTSTRAP_ADMIN_EMAIL=None,
        KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD="secret",
    )
    keycloak = SimpleNamespace(
        is_enabled=lambda: True,
        get_user_by_email=AsyncMock(return_value=None),
        get_user_by_username=AsyncMock(return_value=existing_user),
        create_user=AsyncMock(),
        update_user=AsyncMock(),
        set_password=AsyncMock(),
        set_realm_role=AsyncMock(),
    )
    user_repo = SimpleNamespace(
        upsert_by_keycloak_id=AsyncMock(
            return_value=SimpleNamespace(id=uuid.uuid4(), email="admin@agenticai.local")
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

    assert result["status"] == "exists"
    keycloak.get_user_by_username.assert_awaited_once_with("admin")
    keycloak.create_user.assert_not_awaited()
    keycloak.set_realm_role.assert_not_awaited()
    user_repo.upsert_by_keycloak_id.assert_awaited_once_with(
        "kc-admin-id",
        email="admin@agenticai.local",
        username="admin",
        first_name="Default",
        last_name="Admin",
        role="system-admin",
        is_active=True,
        is_verified=True,
        is_external_keycloak_user=False,
    )
