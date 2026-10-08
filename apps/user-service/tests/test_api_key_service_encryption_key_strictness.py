"""api_key_service's cipher must reject a malformed key, and use its own scope.

_get_fernet used to base64-decode the configured key itself and hand Fernet the
raw decoded bytes -- the wrong input, since Fernet decodes the key internally.
A wrong-length key therefore failed later, inside Fernet's own re-decode of
binary data, with an opaque binascii error instead of a clear one, and a key of
the right length but wrong content was never checked at all. The key is now
scoped to USER_API_KEY_ENCRYPTION_KEY and validated in core.security.encryption.
See test_encryption_key_strictness.py for the sibling in system_settings_service.
"""

from __future__ import annotations

import base64

from error_contract import ConfigurationError
import pytest

from src.core.security import encryption
from src.service import api_key_service


def _valid_key() -> str:
    return base64.urlsafe_b64encode(b"k" * 32).decode()


@pytest.fixture
def scope_key(monkeypatch):
    def _set(key):
        monkeypatch.setenv("USER_API_KEY_ENCRYPTION_KEY", key)
        encryption.reset_ciphers()

    yield _set
    encryption.reset_ciphers()


def test_a_valid_fernet_key_is_accepted(scope_key):
    scope_key(_valid_key())

    assert api_key_service._get_fernet() is not None


@pytest.mark.parametrize("bad", ["short", "k" * 43, "k" * 45, ""])
def test_a_key_that_is_not_a_fernet_key_is_refused(scope_key, bad):
    scope_key(bad)

    with pytest.raises(ConfigurationError):
        api_key_service._get_fernet()


def test_encrypt_then_decrypt_round_trips_with_a_valid_key(scope_key):
    scope_key(_valid_key())

    fernet = api_key_service._get_fernet()
    assert fernet.decrypt(fernet.encrypt(b"a-key-hash")) == b"a-key-hash"
