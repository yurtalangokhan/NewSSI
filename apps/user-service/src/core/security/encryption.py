"""Scope-separated Fernet ciphers for stored secrets.

API-key ciphertext, the secrets inside persisted system settings, and stored
connector configurations are unrelated classes of data, so each is sealed under
its own key. A leaked key opens only its own scope.

"""

from __future__ import annotations

from enum import StrEnum

from config_manager import env
from cryptography.fernet import Fernet
from error_contract import ConfigurationError


class SecretScope(StrEnum):
    """A class of stored secret, named by the config_manager getter holding its key."""

    USER_API_KEY = "USER_API_KEY_ENCRYPTION_KEY"
    SYSTEM_SETTINGS = "SYSTEM_SETTINGS_ENCRYPTION_KEY"
    CONNECTOR_CONFIG = "CONNECTOR_CONFIG_ENCRYPTION_KEY"


_ciphers: dict[SecretScope, Fernet] = {}


def reset_ciphers() -> None:
    """Drop the cached ciphers. For tests that vary the configured keys."""
    _ciphers.clear()


def _fernet(key: str, setting: str) -> Fernet:
    """Build a Fernet, with no stretching.

    A wrong-length key used to be truncated and padded into something Fernet
    accepts, so a mistyped key became a valid-looking one with far less entropy
    than it appears to have. Fernet's own validation is the check.
    """
    try:
        return Fernet(key)
    except (ValueError, TypeError) as exc:
        # Name the offending setting, never its value.
        raise ConfigurationError(details={"setting": setting}) from exc


def get_cipher(scope: SecretScope) -> Fernet:
    cipher = _ciphers.get(scope)
    if cipher is not None:
        return cipher

    key = getattr(env, scope.value)
    if not key:
        raise ConfigurationError(details={"setting": scope.value})

    cipher = _fernet(key, scope.value)
    _ciphers[scope] = cipher
    return cipher
