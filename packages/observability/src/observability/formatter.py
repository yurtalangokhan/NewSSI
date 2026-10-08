"""The one record schema, and the two formatters that render it.

Every service emits the same fields, so one dashboard query or one index mapping
works across the platform. The field set is defined once, here, as
:data:`RECORD_FIELDS`; :func:`build_fields` produces it and both formatters
render from that same function. Format identity is therefore structural: the
text output cannot drift from the JSON output because neither of them owns the
field list.

Absent values are written as ``null`` rather than omitted. A missing key in a
shipped log stream forces a mapping change or a query that fails on documents
that happen to lack the field, and both are worse than an explicit null.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any, ClassVar

from .context import current_context
from .sanitize import mask_fields, sanitize_exception

# The platform field contract. Order is the render order for both formats.
RECORD_FIELDS: tuple[str, ...] = (
    "timestamp",
    "level",
    "service",
    "logger",
    "event",
    "message",
    "request_id",
    "trace_id",
    "user_id",
    "module",
    "function",
    "line",
    "operation",
    "dependency",
    "attempt",
    "max_attempts",
    "elapsed_ms",
    "status",
    "error",
)

# Fields read straight off the record rather than from the correlation context.
# A call site that sets one of these explicitly wins over the ambient context.
_RECORD_SOURCED_FIELDS = (
    "event",
    "operation",
    "dependency",
    "attempt",
    "max_attempts",
    "elapsed_ms",
    "status",
)

# Attributes the standard library puts on every LogRecord. Anything else in the
# record's namespace was supplied by the call site through ``extra``, and is
# rendered after the contract fields so a call site can add context without
# being able to displace a contract field.
_STANDARD_RECORD_ATTRS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)

_LEVEL_COLORS = {
    "DEBUG": "\033[36m",
    "INFO": "\033[32m",
    "WARNING": "\033[33m",
    "ERROR": "\033[31m",
    "CRITICAL": "\033[35m",
    "RESET": "\033[0m",
}


def _ambient_trace_id(context: Any) -> str | None:
    """The trace id a record should carry from its surroundings.

    The correlation context wins: the middleware bound it deliberately. When it
    is empty and telemetry is on, the active span provides it, which is what
    joins a background job's records to the trace it runs inside. With telemetry
    off this never touches the SDK.
    """
    if context.trace_id:
        return context.trace_id
    from .otel import current_trace_id, is_enabled

    if is_enabled():
        return current_trace_id()
    return None


def build_fields(record: logging.LogRecord, *, service_name: str) -> dict[str, Any]:
    """Return the record as the platform field contract.

    This is the single place the schema is assembled. Sensitive values are masked
    here, before any destination sees them, which is why no call site has to
    remember to sanitize.
    """
    context = current_context()
    extra = {
        key: value
        for key, value in vars(record).items()
        if key not in _STANDARD_RECORD_ATTRS and key not in RECORD_FIELDS
    }

    fields: dict[str, Any] = {
        "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
        "level": record.levelname,
        "service": getattr(record, "service", None) or service_name,
        "logger": record.name,
        "event": getattr(record, "event", None),
        "message": record.getMessage(),
        "request_id": getattr(record, "request_id", None) or context.request_id,
        "trace_id": getattr(record, "trace_id", None) or _ambient_trace_id(context),
        "user_id": getattr(record, "user_id", None) or context.user_id,
        "module": record.module,
        "function": record.funcName,
        "line": record.lineno,
        "operation": getattr(record, "operation", None),
        "dependency": getattr(record, "dependency", None),
        "attempt": getattr(record, "attempt", None),
        "max_attempts": getattr(record, "max_attempts", None),
        "elapsed_ms": getattr(record, "elapsed_ms", None),
        "status": getattr(record, "status", None),
    }
    # An explicit null, not an omitted key: the contract says which fields a
    # record carries, so a consumer never has to test for presence.
    fields["error"] = sanitize_exception(record.exc_info[1]) if record.exc_info else None

    return mask_fields({**fields, **extra})


class BaseFormatter(logging.Formatter):
    """Shared construction for both output formats."""

    def __init__(self, *, service_name: str, include_source: bool = True) -> None:
        super().__init__()
        self._service_name = service_name
        self._include_source = include_source

    def fields_for(self, record: logging.LogRecord) -> dict[str, Any]:
        """Return the masked contract fields for one record."""
        return build_fields(record, service_name=self._service_name)


class JsonFormatter(BaseFormatter):
    """Render records as one JSON object per line.

    One object per line is what makes a stream shippable: a collector can read
    records one at a time, and a truncated line loses one record rather than
    corrupting every record after it.
    """

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(self.fields_for(record), separators=(",", ":"), default=str)


class TextFormatter(BaseFormatter):
    """Render records for a human reading a terminal or a file.

    The same field values as the JSON output, in the same order, so a developer
    reading a text line sees exactly what a platform would index. A text line is
    free to omit a field that is unset, because nothing downstream parses it; the
    JSON output cannot, which is why the field set is assembled once and shared.
    """

    _SOURCE_FIELDS: ClassVar[tuple[str, ...]] = ("module", "function", "line")

    def __init__(
        self,
        *,
        service_name: str,
        include_source: bool = True,
        use_colors: bool = True,
    ) -> None:
        super().__init__(service_name=service_name, include_source=include_source)
        # Color is only useful on a terminal; a redirected stream or a file gets
        # escape codes nobody asked for.
        self._use_colors = use_colors and sys.stdout.isatty()

    def format(self, record: logging.LogRecord) -> str:
        fields = self.fields_for(record)
        contract = set(RECORD_FIELDS)
        color = _LEVEL_COLORS.get(fields["level"], "") if self._use_colors else ""
        reset = _LEVEL_COLORS["RESET"] if self._use_colors else ""

        parts = [
            fields["timestamp"],
            f"{color}{fields['level']:<8}{reset}",
            f"{fields['service']:<14}",
            fields["message"],
        ]

        bits = [
            _bit("request_id", fields["request_id"]),
            _bit("event", fields["event"]),
            _bit("operation", fields["operation"]),
            _bit("dependency", fields["dependency"]),
            _attempt_bit(fields),
            _bit("status", fields["status"]),
            _bit("elapsed_ms", fields["elapsed_ms"]),
        ]
        # Call-site context an operator would otherwise have to open the source
        # file to find, e.g. the error_code that classifies a failure.
        bits.extend(_bit(key, value) for key, value in fields.items() if key not in contract)
        present = [bit for bit in bits if bit]
        if present:
            parts.append(" | ".join(present))

        if self._include_source:
            source = " ".join(str(fields[name]) for name in self._SOURCE_FIELDS)
            parts.append(f"[{source}]")

        line = " ".join(part for part in parts if part)
        if fields["error"]:
            error = fields["error"]
            line = f"{line}\n    {error['exception_type']}: {error['exception_message']}"
        return line


def _bit(key: str, value: Any) -> str | None:
    """Render one field as ``key=value``, or nothing when it is unset."""
    if value is None or value == "":
        return None
    return f"{key}={value}"


def _attempt_bit(fields: dict[str, Any]) -> str | None:
    """Render the attempt counter, showing the ceiling when it is known."""
    attempt = fields.get("attempt")
    if attempt is None:
        return None
    max_attempts = fields.get("max_attempts")
    if max_attempts is None:
        return f"attempt={attempt}"
    return f"attempt={attempt}/{max_attempts}"
