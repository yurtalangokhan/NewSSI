"""The encryption key must be a real Fernet key, not padded into one.

A key of the wrong length was silently stretched — truncated to 32 bytes and
right-padded with b"0" — into something Fernet would accept. That turns a
short or mistyped key into a valid-looking one with far less entropy than it
appears to have, and it does so quietly at the point of first use rather than
failing at startup where an operator would see it.
"""

from __future__ import annotations

import base64

from error_contract import ConfigurationError
import pytest

from src.core.security import encryption
from src.service.system_settings_service import _fernet


def _valid_key() -> str:
    return base64.urlsafe_b64encode(b"k" * 32).decode()


@pytest.fixture
def scope_key(monkeypatch):
    def _set(key):
        monkeypatch.setenv("SYSTEM_SETTINGS_ENCRYPTION_KEY", key)
        encryption.reset_ciphers()

    yield _set
    encryption.reset_ciphers()


def test_a_valid_fernet_key_is_accepted(scope_key):
    scope_key(_valid_key())

    assert _fernet() is not None


@pytest.mark.parametrize("bad", ["short", "k" * 43, "k" * 45, ""])
def test_a_key_that_is_not_a_fernet_key_is_refused(scope_key, bad):
    scope_key(bad)

    with pytest.raises(ConfigurationError):
        _fernet()
