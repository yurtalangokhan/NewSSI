"""Scope-separated ciphers, and the key validation that makes them safe."""

import pytest
from cryptography.fernet import Fernet

from security import FernetKeyError, ScopedCipherStore, mask_secret

KEY_A = Fernet.generate_key().decode()
KEY_B = Fernet.generate_key().decode()
LEGACY = Fernet.generate_key().decode()


def store(keys: dict[str, str], *, legacy: str | None = None) -> ScopedCipherStore:
    return ScopedCipherStore(lambda name: keys.get(name), resolve_legacy_key=lambda: legacy)


def test_round_trip_within_a_scope():
    s = store({"A": KEY_A})
    assert s.decrypt("A", s.encrypt("A", "hunter2")) == "hunter2"


def test_scopes_are_separated():
    s = store({"A": KEY_A, "B": KEY_B})
    token = s.encrypt("A", "secret")
    with pytest.raises(FernetKeyError):
        s.decrypt("B", token)


def test_missing_key_is_rejected():
    with pytest.raises(FernetKeyError, match="required for secret storage"):
        store({}).encrypt("A", "x")


def test_blank_key_is_rejected():
    with pytest.raises(FernetKeyError):
        store({"A": "   "}).encrypt("A", "x")


def test_wrong_length_key_is_rejected_not_stretched():
    """A mistyped key must fail loudly, not become a weak valid-looking one."""
    with pytest.raises(FernetKeyError, match="not a valid Fernet key"):
        store({"A": "too-short"}).encrypt("A", "x")


def test_non_base64_key_is_rejected():
    with pytest.raises(FernetKeyError, match="not a valid Fernet key"):
        store({"A": "!" * 44}).encrypt("A", "x")


def test_legacy_key_still_reads_old_rows():
    old = store({"A": KEY_A})
    token = old.encrypt("A", "written-before-the-split")
    rotated = store({"A": KEY_B}, legacy=KEY_A)
    assert rotated.decrypt("A", token) == "written-before-the-split"


def test_writes_use_the_scope_key_not_the_legacy_key():
    """The legacy key is a read fallback; new writes must not use it."""
    s = store({"A": KEY_B}, legacy=KEY_A)
    token = s.encrypt("A", "new")
    assert store({"A": KEY_B}).decrypt("A", token) == "new"
    with pytest.raises(FernetKeyError):
        store({"A": KEY_A}).decrypt("A", token)


def test_missing_scope_key_does_not_fall_back_to_legacy():
    """Falling back would quietly undo the separation the scope exists for."""
    with pytest.raises(FernetKeyError, match="required for secret storage"):
        store({}, legacy=LEGACY).encrypt("A", "x")


def test_reset_drops_cached_ciphers():
    keys = {"A": KEY_A}
    s = store(keys)
    s.encrypt("A", "x")
    keys["A"] = KEY_B
    s.reset()
    token = s.encrypt("A", "y")
    assert store({"A": KEY_B}).decrypt("A", token) == "y"


def test_cipher_is_cached_per_scope():
    s = store({"A": KEY_A})
    assert s.cipher("A") is s.cipher("A")


@pytest.mark.parametrize(
    ("plaintext", "expected"),
    [("abcd", "****"), ("abc", "****"), ("", "****"), ("abcdefgh", "****efgh")],
)
def test_mask_secret_keeps_at_most_the_last_four(plaintext, expected):
    assert mask_secret(plaintext) == expected
