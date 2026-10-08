from pathlib import Path

import pytest
from localization import init_localization

init_localization(Path(__file__).resolve().parents[1] / "locales")


@pytest.fixture(autouse=True)
async def _dispose_db_engine_between_tests():
    # Each test gets its own event loop, but the pooled engine is a
    # process-wide singleton; without disposing it, a connection checked
    # out in one test gets reused/closed from a different, already-closed
    # loop in a later one.
    yield
    from security import close_all

    await close_all()
    from src.core.database.engine import close_db_engine

    await close_db_engine()


@pytest.fixture(autouse=True)
def _reset_directory_caches():
    """Role index and role distribution are cached per process; keep tests isolated."""
    from src.repository.user_repository import UserRepository
    from src.service import role_distribution
    from src.service.keycloak_service import KeycloakService

    KeycloakService._admin_token_cache.clear()
    KeycloakService._client_uuid_cache.clear()
    UserRepository.invalidate_role_index()
    role_distribution._snapshot = None
    yield
    UserRepository.invalidate_role_index()
    role_distribution._snapshot = None


@pytest.fixture(autouse=True)
def _scope_encryption_keys(monkeypatch):
    """A fresh key per scope, per test.

    Without this the suite silently encrypts with whatever configs/.env holds,
    so a developer without that file saw unrelated failures and a developer with
    one was exercising their real key.
    """
    from cryptography.fernet import Fernet

    from src.core.security import encryption

    monkeypatch.setenv("USER_API_KEY_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("SYSTEM_SETTINGS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CONNECTOR_CONFIG_ENCRYPTION_KEY", Fernet.generate_key().decode())
    encryption.reset_ciphers()
    yield
    encryption.reset_ciphers()
