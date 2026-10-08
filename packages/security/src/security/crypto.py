"""Scope-separated symmetric encryption.

Every class of stored secret is sealed under its own key, so a leaked key opens
only its own data. A scope is named by the configuration getter that holds its
key, and it is the *service* that names its scopes — this module resolves a key
by whatever callable it is given rather than reading configuration itself.

During a migration away from a superseded shared key, a scope's cipher can be a
``MultiFernet`` over ``[scope key, legacy key]``: writes always use the scope
key, while reads fall back to the legacy key for rows written before the split.
A re-encryption script rewrites those rows, after which the fallback is dropped.

Key validation is not optional and not the caller's job. A wrong-length key
must not be truncated or padded into something Fernet accepts, because a
mistyped key then becomes a valid-looking one with far less entropy than it
appears to have.
"""

from __future__ import annotations

from collections.abc import Callable

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

KeyResolver = Callable[[str], str | None]


class FernetKeyError(ValueError):
    """A configured key is missing, blank, or not a valid Fernet key."""


def _build_fernet(key: str, name: str) -> Fernet:
    """Build a Fernet from *key*, with no stretching.

    Fernet's own validation is the check. Anything that reshapes the key first
    hides a configuration mistake behind a working cipher.
    """
    try:
        return Fernet(key)
    except (ValueError, TypeError) as exc:
        raise FernetKeyError(
            f"{name} is not a valid Fernet key (expected 32 url-safe base64-encoded bytes)."
        ) from exc


def mask_secret(plaintext: str) -> str:
    """Mask a secret for display, keeping at most its last four characters."""
    if len(plaintext) <= 4:
        return "****"
    return "*" * (len(plaintext) - 4) + plaintext[-4:]


class ScopedCipherStore:
    """Cached per-scope ciphers for one process.

    The store is a per-service object rather than module state so that two
    services in one process, or two test suites, cannot reach each other's
    cached ciphers. :meth:`reset` exists for tests that vary the configured keys.
    """

    __slots__ = ("_ciphers", "_resolve_key", "_resolve_legacy_key")

    def __init__(
        self,
        resolve_key: KeyResolver,
        *,
        resolve_legacy_key: Callable[[], str | None] | None = None,
    ) -> None:
        self._resolve_key = resolve_key
        self._resolve_legacy_key = resolve_legacy_key
        self._ciphers: dict[str, MultiFernet] = {}

    def reset(self) -> None:
        """Drop cached ciphers. For tests that vary the configured keys."""
        self._ciphers.clear()

    def cipher(self, scope: str) -> MultiFernet:
        """Return the cipher for *scope*, building and caching it on first use."""
        cached = self._ciphers.get(scope)
        if cached is not None:
            return cached

        key = self._resolve_key(scope)
        if not key:
            # Deliberately not falling back to the legacy key here: that would
            # quietly undo the separation this scope exists to provide.
            raise FernetKeyError(f"{scope} is required for secret storage")

        keys = [_build_fernet(key, scope)]
        # Resolved per build rather than captured once: the legacy key is
        # configuration like any other, and freezing it at import time would
        # hide a key that has since been set or removed.
        legacy = self._resolve_legacy_key() if self._resolve_legacy_key else None
        if legacy:
            keys.append(_build_fernet(legacy, "LEGACY_ENCRYPTION_KEY"))

        cipher = MultiFernet(keys)
        self._ciphers[scope] = cipher
        return cipher

    def encrypt(self, scope: str, plaintext: str) -> str:
        return self.cipher(scope).encrypt(plaintext.encode()).decode()

    def decrypt(self, scope: str, token: str) -> str:
        try:
            return self.cipher(scope).decrypt(token.encode()).decode()
        except InvalidToken as exc:
            raise FernetKeyError(
                f"Failed to decrypt a {scope} secret; encryption key may have rotated"
            ) from exc


__all__ = ["FernetKeyError", "KeyResolver", "ScopedCipherStore", "mask_secret"]
