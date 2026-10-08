"""API-key ciphertext and system-settings ciphertext must not share a key."""

from __future__ import annotations

from error_contract import ConfigurationError
import pytest
from cryptography.fernet import Fernet, InvalidToken

from src.core.security import encryption
from src.core.security.encryption import SecretScope, get_cipher

SCOPE_FIELDS = {
    SecretScope.USER_API_KEY: "USER_API_KEY_ENCRYPTION_KEY",
    SecretScope.SYSTEM_SETTINGS: "SYSTEM_SETTINGS_ENCRYPTION_KEY",
    SecretScope.CONNECTOR_CONFIG: "CONNECTOR_CONFIG_ENCRYPTION_KEY",
}


@pytest.fixture
def scoped_keys(monkeypatch):
    for field in SCOPE_FIELDS.values():
        monkeypatch.setenv(field, Fernet.generate_key().decode())
    encryption.reset_ciphers()
    yield
    encryption.reset_ciphers()


def test_round_trips_within_a_scope(scoped_keys):
    for scope in SecretScope:
        cipher = get_cipher(scope)
        assert cipher.decrypt(cipher.encrypt(b"s3cret")) == b"s3cret"


def test_a_scope_cannot_read_another_scopes_ciphertext(scoped_keys):
    token = get_cipher(SecretScope.USER_API_KEY).encrypt(b"api-key-hash")

    with pytest.raises(InvalidToken):
        get_cipher(SecretScope.SYSTEM_SETTINGS).decrypt(token)


def test_legacy_key_cannot_decrypt_pre_migration_ciphertext(monkeypatch):
    legacy = Fernet.generate_key().decode()
    token = Fernet(legacy.encode()).encrypt(b"old-secret")

    for field in SCOPE_FIELDS.values():
        monkeypatch.setenv(field, Fernet.generate_key().decode())
    monkeypatch.setenv("LEGACY_ENCRYPTION_KEY", legacy)
    encryption.reset_ciphers()

    for scope in SecretScope:
        with pytest.raises(InvalidToken):
            get_cipher(scope).decrypt(token)

    encryption.reset_ciphers()


def test_a_malformed_scope_key_reports_the_variable(monkeypatch):
    monkeypatch.setenv("USER_API_KEY_ENCRYPTION_KEY", "not-a-fernet-key")
    encryption.reset_ciphers()

    with pytest.raises(ConfigurationError) as raised:
        get_cipher(SecretScope.USER_API_KEY)
    assert raised.value.details["setting"] == "USER_API_KEY_ENCRYPTION_KEY"

    encryption.reset_ciphers()


def test_a_missing_scope_key_is_an_error(monkeypatch):
    monkeypatch.delenv("SYSTEM_SETTINGS_ENCRYPTION_KEY", raising=False)
    encryption.reset_ciphers()

    with pytest.raises(ConfigurationError) as raised:
        get_cipher(SecretScope.SYSTEM_SETTINGS)
    assert raised.value.details["setting"] == "SYSTEM_SETTINGS_ENCRYPTION_KEY"

    encryption.reset_ciphers()
