"""Keeps credentials out of what is stored or shown about a connector.

Text first, such as a job's error. HTTP clients and database drivers quote the
address they talked to. A key in its query string, a password in its user info
or a configured secret repeated by the remote system would otherwise travel
with the message into the job store and to whoever may read a sync's status.

Then configuration. A mapping such as request headers holds credentials next to
ordinary settings, and only the name of a key tells the two apart.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping
from typing import Any

MASK = "***"

#: Shorter values cannot be told from ordinary text; masking them only garbles it.
MIN_SECRET_LENGTH = 4

_URL = r"\b[a-zA-Z][a-zA-Z0-9+.\-]*://"
# Greedy up to the last "@" of the authority: an unescaped "@" in a password stays covered.
_URL_PASSWORD = re.compile(rf"(?P<user>{_URL}[^\s/?#@:'\"<>]*):[^\s/?#'\"<>]+@")
_URL_QUERY = re.compile(rf"(?P<address>{_URL}[^\s?#'\"<>]+)\?[^\s#'\"<>]*")

#: What gives a credential away wherever it stands in a key name.
_SENSITIVE_PARTS = (
    "password",
    "passwd",
    "passphrase",
    "secret",
    "token",
    "authorization",
    "apikey",
    "accesskey",
    "privatekey",
    "credential",
    "cookie",
    "signature",
)
#: Short names count only as a whole word: ``key`` is one, ``monkey`` is not.
_SENSITIVE_WORDS = frozenset({"auth", "key", "pwd", "pass", "sig", "sas", "jwt", "bearer"})
_WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")
_EMPTY: tuple[Any, ...] = (None, "", {}, [])


def redact_secrets(text: str, secrets: Iterable[str] = ()) -> str:
    """``text`` without ``secrets``, URL passwords and URL query strings."""
    values = {secret for secret in secrets if len(secret) >= MIN_SECRET_LENGTH}
    # Longest first: a value that contains another one must go as a whole.
    for secret in sorted(values, key=len, reverse=True):
        text = text.replace(secret, MASK)
    text = _URL_PASSWORD.sub(rf"\g<user>:{MASK}@", text)
    return _URL_QUERY.sub(rf"\g<address>?{MASK}", text)


def is_sensitive_key(name: str) -> bool:
    """Does a mapping key of this name look like it holds a credential?

    A guess from the name alone: ``Authorization``, ``X-Api-Key``,
    ``client_secret`` and ``fs.s3a.secret.key`` do, ``Accept`` and ``limit`` do
    not. A credential kept under a name that says nothing is not recognised.
    """
    squeezed = "".join(char for char in name.lower() if char.isalnum())
    if any(part in squeezed for part in _SENSITIVE_PARTS):
        return True
    return any(word.lower() in _SENSITIVE_WORDS for word in _WORD.findall(name))


def mask_sensitive_values(value: Any, mask: str) -> Any:
    """A copy of ``value`` with ``mask`` in place of what its credential keys hold.

    Mappings and lists are walked to any depth. Whatever such a key holds goes
    as a whole; an empty value stays, so "not set" can be told from "hidden".
    """
    if isinstance(value, Mapping):
        return {
            key: mask
            if is_sensitive_key(str(key)) and item not in _EMPTY
            else mask_sensitive_values(item, mask)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [mask_sensitive_values(item, mask) for item in value]
    return value


def sensitive_values(value: Any, *, _sensitive: bool = False) -> Iterator[str]:
    """The strings the credential keys of ``value`` hold, for :func:`redact_secrets`.

    One that carries a scheme (``Bearer abc``) is given without it as well: a
    remote system may quote the credential either way.
    """
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield from sensitive_values(item, _sensitive=_sensitive or is_sensitive_key(str(key)))
    elif isinstance(value, list):
        for item in value:
            yield from sensitive_values(item, _sensitive=_sensitive)
    elif _sensitive and isinstance(value, str) and value:
        yield value
        words = value.split()
        if len(words) == 2:
            yield words[1]
