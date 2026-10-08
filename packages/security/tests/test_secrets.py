"""The mask must never be mistaken for the secret."""

import pytest
from pydantic import SecretBytes, SecretStr

from security import require_secret, reveal_secret


def test_secret_str_is_unwrapped() -> None:
    assert reveal_secret(SecretStr("hunter2")) == "hunter2"


def test_the_mask_never_leaks_through() -> None:
    """`str(SecretStr(...))` is truthy, which is what makes the bug silent."""
    secret = SecretStr("hunter2")
    assert str(secret) != "hunter2"

    assert "*" not in reveal_secret(secret)


def test_plain_values_pass_through() -> None:
    assert reveal_secret("hunter2") == "hunter2"


def test_secret_bytes_is_unwrapped() -> None:
    # str(SecretBytes(...)) is "b'**********'" -- as truthy and as wrong an
    # answer as str(SecretStr(...)), just for pydantic's other secret type.
    assert reveal_secret(SecretBytes(b"hunter2")) == "hunter2"


def test_secret_bytes_mask_never_leaks_through() -> None:
    secret = SecretBytes(b"hunter2")
    assert "*" not in reveal_secret(secret)


def test_surrounding_whitespace_is_stripped() -> None:
    assert reveal_secret(SecretStr("  hunter2  ")) == "hunter2"


@pytest.mark.parametrize(
    "value",
    [None, "", "   ", SecretStr(""), SecretStr("   "), SecretBytes(b""), SecretBytes(b"   ")],
)
def test_unset_and_blank_collapse_to_none(value) -> None:
    assert reveal_secret(value) is None


def test_require_secret_returns_the_plaintext() -> None:
    assert require_secret(SecretStr("hunter2"), "AUTHENTICATION_SECRET") == "hunter2"


@pytest.mark.parametrize("value", [None, "", SecretStr("")])
def test_require_secret_names_the_missing_setting(value) -> None:
    with pytest.raises(ValueError, match="AUTHENTICATION_SECRET"):
        require_secret(value, "AUTHENTICATION_SECRET")
