"""Secrets held as ``SecretStr`` must reach consumers as plaintext.

``str(SecretStr("x"))`` returns ``'**********'`` — a truthy value — so a masked
secret silently wins over a correct one instead of failing loudly. These tests
pin the seams where settings-sourced secrets are converted for use.
"""

from pydantic import SecretStr
from security import reveal_secret

from src.main import _admin_password
from src.service.system_settings_service import _configured_value


class _Settings:
    def __init__(self, password):
        self.KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD = password


def test_reveal_secret_unwraps_secret_str() -> None:
    assert reveal_secret(SecretStr("hunter2")) == "hunter2"


def test_reveal_secret_passes_through_plain_values() -> None:
    assert reveal_secret("hunter2") == "hunter2"
    assert reveal_secret(None) is None
    assert reveal_secret("") is None


def test_admin_password_is_not_masked() -> None:
    assert _admin_password(_Settings(SecretStr("  hunter2  "))) == "hunter2"


def test_admin_password_is_none_when_unset() -> None:
    assert _admin_password(_Settings(None)) is None
    assert _admin_password(_Settings(SecretStr("   "))) is None


def test_configured_value_prefers_real_secret_over_mask() -> None:
    assert _configured_value(None, SecretStr("real-secret")) == "real-secret"


def test_configured_value_skips_empty_secret_and_falls_through() -> None:
    assert _configured_value(SecretStr(""), "fallback") == "fallback"
