"""Each class of stored secret must be sealed under its own key."""

from __future__ import annotations

import pytest
from config_manager import env
from cryptography.fernet import Fernet
from core.security import encryption
from core.security.encryption import SecretScope, decrypt_secret, encrypt_secret

SCOPE_FIELDS = {
    SecretScope.LLM_PROVIDER_API: "LLM_PROVIDER_API_ENCRYPTION_KEY",
    SecretScope.MCP_CREDENTIAL: "MCP_CREDENTIAL_ENCRYPTION_KEY",
    SecretScope.MCP_OAUTH: "MCP_OAUTH_ENCRYPTION_KEY",
    SecretScope.MAIL_CONFIG: "MAIL_CONFIG_ENCRYPTION_KEY",
}


@pytest.fixture
def scoped_keys(monkeypatch):
    """A distinct key per scope."""
    for field in SCOPE_FIELDS.values():
        monkeypatch.setenv(field, Fernet.generate_key().decode())
    encryption.reset_ciphers()
    yield
    encryption.reset_ciphers()


def test_every_scope_has_its_own_key(scoped_keys):
    assert len({getattr(env, field) for field in SCOPE_FIELDS.values()}) == len(SCOPE_FIELDS)


@pytest.mark.parametrize("scope", list(SecretScope))
def test_round_trips_within_a_scope(scoped_keys, scope):
    assert decrypt_secret(scope, encrypt_secret(scope, "s3cret")) == "s3cret"


def test_a_scope_cannot_read_another_scopes_ciphertext(scoped_keys):
    token = encrypt_secret(SecretScope.MAIL_CONFIG, "smtp-password")

    for other in SecretScope:
        if other is SecretScope.MAIL_CONFIG:
            continue
        with pytest.raises(ValueError):
            decrypt_secret(other, token)


def test_legacy_key_cannot_decrypt_pre_migration_ciphertext(monkeypatch):
    legacy = Fernet.generate_key().decode()
    token = Fernet(legacy.encode()).encrypt(b"old-secret").decode()

    for field in SCOPE_FIELDS.values():
        monkeypatch.setenv(field, Fernet.generate_key().decode())
    monkeypatch.setenv("LEGACY_ENCRYPTION_KEY", legacy)
    encryption.reset_ciphers()

    for scope in SecretScope:
        with pytest.raises(ValueError):
            decrypt_secret(scope, token)

    encryption.reset_ciphers()


def test_a_missing_scope_key_is_an_error(monkeypatch):
    monkeypatch.delenv("MAIL_CONFIG_ENCRYPTION_KEY", raising=False)
    encryption.reset_ciphers()

    with pytest.raises(RuntimeError, match="MAIL_CONFIG_ENCRYPTION_KEY"):
        encrypt_secret(SecretScope.MAIL_CONFIG, "x")

    encryption.reset_ciphers()
