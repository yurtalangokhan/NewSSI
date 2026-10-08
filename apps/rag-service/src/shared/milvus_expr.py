"""Milvus boolean expression construction.

Milvus has no parameter binding for boolean expressions -- a filter is
always a string the server parses as an expression. The only safe way to
embed a caller-supplied value into one is a strict allow-list on both the
field/key and the value; anything that is not identifier-shaped never
reaches the expression at all.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

_IDENTIFIER = re.compile(r"^[A-Za-z0-9_\-]{1,128}$")
_KEY = re.compile(r"^[A-Za-z0-9_]{1,64}$")


class InvalidExpressionValueError(ValueError):
    """Raised when a key or value cannot be safely embedded."""


def metadata_path(field: str, key: str) -> str:
    """Build `field["key"]`, rejecting a field or key that is not a plain name.

    The spelling the filters below use, and the one a JSON path index on that
    key has to be created with.
    """
    if not _KEY.match(field or ""):
        raise InvalidExpressionValueError(f"Invalid metadata field {field!r}")
    if not _KEY.match(key or ""):
        raise InvalidExpressionValueError(f"Invalid metadata key {key!r}")
    return f'{field}["{key}"]'


def _quoted(value: str) -> str:
    """Build `"value"`, rejecting anything not identifier-shaped."""
    if not _IDENTIFIER.match(value or ""):
        raise InvalidExpressionValueError("Value is not an identifier")
    return f'"{value}"'


def metadata_equals(field: str, key: str, value: str) -> str:
    """Build `field["key"] == "value"`, rejecting anything not identifier-shaped."""
    return f"{metadata_path(field, key)} == {_quoted(value)}"


def metadata_in(field: str, key: str, values: Sequence[str]) -> str:
    """Build `field["key"] in ["a", "b"]` under the allow-list of metadata_equals.

    An empty list is rejected as well: a filter that can match nothing is a
    mistake of the caller, not a query worth sending.
    """
    path = metadata_path(field, key)
    if not values:
        raise InvalidExpressionValueError("No values to match")
    return f"{path} in [{', '.join(_quoted(value) for value in values)}]"


def metadata_missing_or_not_equals(field: str, key: str, value: str) -> str:
    """Build `(not exists field["key"]) or field["key"] != "value"`.

    Milvus skips a row whose JSON lacks the key when it evaluates `!=`, so the
    rows written before the key existed are named separately.
    """
    path = metadata_path(field, key)
    return f"(not exists {path}) or {path} != {_quoted(value)}"
