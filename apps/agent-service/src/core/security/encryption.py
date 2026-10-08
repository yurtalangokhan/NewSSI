"""Fernet-based symmetric encryption for secret storage.

Every class of stored secret is sealed under its own key, so a leaked key opens
only its own data. `SecretScope` names both the class and the config_manager
getter holding its key. Cipher mechanics live in the shared `security` package.
"""

from __future__ import annotations

from enum import StrEnum

from config_manager import env
from cryptography.fernet import InvalidToken, MultiFernet
from security import FernetKeyError, ScopedCipherStore, mask_secret


class SecretScope(StrEnum):
    """A class of stored secret, named by the config_manager getter holding its key."""

    LLM_PROVIDER_API = "LLM_PROVIDER_API_ENCRYPTION_KEY"
    MCP_CREDENTIAL = "MCP_CREDENTIAL_ENCRYPTION_KEY"
    MCP_OAUTH = "MCP_OAUTH_ENCRYPTION_KEY"
    MAIL_CONFIG = "MAIL_CONFIG_ENCRYPTION_KEY"


_store = ScopedCipherStore(lambda scope: getattr(env, scope))


def reset_ciphers() -> None:
    """Drop the cached ciphers. For tests that vary the configured keys."""
    _store.reset()


def _cipher(scope: SecretScope) -> MultiFernet:
    """The scope's cipher, after this service's own required-key check.

    A missing scope key is a fatal misconfiguration for this service, and it is
    reported as a RuntimeError naming the setting — the contract callers and
    operators already handle. The check is deliberately *not* a fallback to the
    legacy key, which would undo the separation the scope exists to provide.
    """
    if not getattr(env, scope.value):
        raise RuntimeError(f"{scope.value} is required for secret storage")
    return _store.cipher(scope.value)


def encrypt_secret(scope: SecretScope, plaintext: str) -> str:
    return _cipher(scope).encrypt(plaintext.encode()).decode()


def decrypt_secret(scope: SecretScope, token: str) -> str:
    try:
        return _cipher(scope).decrypt(token.encode()).decode()
    except InvalidToken:
        raise ValueError(f"Failed to decrypt a {scope.name} secret; encryption key may have rotated") from None
    except FernetKeyError as exc:
        # Raised by the store for a key that is set but unusable.
        raise ValueError(f"Failed to decrypt a {scope.name} secret; encryption key may have rotated") from exc


def encrypt_api_key(plaintext: str) -> str:
    return encrypt_secret(SecretScope.LLM_PROVIDER_API, plaintext)


def decrypt_api_key(token: str) -> str:
    try:
        return decrypt_secret(SecretScope.LLM_PROVIDER_API, token)
    except ValueError as exc:
        raise ValueError("Failed to decrypt API key — key may have rotated") from exc


def mask_api_key(plaintext: str) -> str:
    return mask_secret(plaintext)
