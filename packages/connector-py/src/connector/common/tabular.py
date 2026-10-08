"""Shared pieces of the table-shaped sources (SQL databases and warehouses).

They all do the same things around their own driver: describe a table as a
stream, quote identifiers, turn driver values into JSON and back, and read
``WHERE cursor > ? ORDER BY cursor`` incrementally.
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from collections.abc import Callable, Mapping
from typing import Any

from ..models import Stream, SyncMode

CHECKPOINT_ROWS = 10_000
"""An ordered table read saves its position about this often (see ``CursorTracker``)."""

_JSON_NATIVE = (str, int, float, bool, type(None))


def to_json_scalar(value: Any, default: Callable[[Any], Any] | None = None) -> Any:
    """A driver value as something ``json.dumps`` accepts.

    ``default`` handles types this function does not know (a driver's own id
    type); without it they pass through unchanged.
    """
    if isinstance(value, _JSON_NATIVE):
        return value
    if isinstance(value, dt.datetime | dt.date | dt.time):
        return value.isoformat()
    if isinstance(value, dt.timedelta):
        return value.total_seconds()
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, bytes | bytearray | memoryview):
        return bytes(value).hex()
    return default(value) if default is not None else value


def to_json_value(value: Any, default: Callable[[Any], Any] | None = None) -> Any:
    """:func:`to_json_scalar`, applied through arrays, structs and maps."""
    if isinstance(value, Mapping):
        return {str(k): to_json_value(v, default) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [to_json_value(v, default) for v in value]
    return to_json_scalar(value, default)


def from_json_scalar(value: Any) -> Any:
    """A stored cursor as a query parameter: ISO timestamps become ``datetime`` again.

    The stored value does not say what type its column has. Any text that parses
    as an ISO date or time is therefore sent as a timestamp, which makes a text
    column holding date-like strings unusable as a cursor.
    """
    if isinstance(value, str):
        try:
            return dt.datetime.fromisoformat(value)
        except ValueError:
            return value
    return value


def is_exact_cursor(raw: Any) -> bool:
    """Does Python compare this driver value the way the database sorts it?

    True for numbers and temporal values. Text is sorted by the column's
    collation, which Python does not know, so it is never used to decide that
    "all rows with this value have been read".
    """
    return not isinstance(raw, str | bytes | bytearray | memoryview)


def table_stream(
    name: str,
    properties: Mapping[str, Any],
    *,
    namespace: str | None = None,
    cursor: str | None = None,
    primary_key: list[list[str]] | None = None,
) -> Stream:
    """The stream of one table. A configured ``cursor`` column makes it incremental."""
    return Stream(
        name=name,
        namespace=namespace,
        json_schema={"type": "object", "properties": dict(properties)},
        supported_sync_modes=[SyncMode.FULL_REFRESH] + ([SyncMode.INCREMENTAL] if cursor else []),
        source_defined_cursor=bool(cursor),
        default_cursor_field=[cursor] if cursor else [],
        source_defined_primary_key=primary_key or [],
    )


# ---- identifier quoting: names come from configuration and discovery, never trust them ----


def ansi_ident(name: str) -> str:
    """``"name"`` (PostgreSQL and standard SQL)."""
    return '"' + name.replace('"', '""') + '"'


def backtick_ident(name: str) -> str:
    """```name``` (MySQL, ClickHouse, Spark)."""
    return "`" + name.replace("`", "``") + "`"


def bracket_ident(name: str) -> str:
    """``[name]`` (SQL Server)."""
    return "[" + name.replace("]", "]]") + "]"
