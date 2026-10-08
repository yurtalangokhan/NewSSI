"""Per-request correlation context for every log record.

One request produces one identifier, and every record written while handling it
carries that identifier. The value lives in a :class:`~contextvars.ContextVar`
so a service sets it once, in one middleware, and the ~170 call sites need no
change and cannot forget to pass it.

An inbound correlation header is preserved so the identifier matches the edge
and any service upstream. When the header is absent the service generates one.
The same value is injected into outbound requests, which is what makes a single
identifier follow a request across every service it touches.

The header is untrusted input. It is length-limited and character-filtered
before it reaches a log line, so a caller cannot inject a newline that would
forge an extra log record, nor a field separator that would corrupt the payload.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from uuid import uuid4

# Checked in order, so an explicit request id wins over a generic correlation id.
CORRELATION_HEADERS = ("x-request-id", "x-correlation-id")

# The names a correlation value is emitted under. Kept as constants because a
# value that is read and written under two different spellings breaks the chain
# silently, and the spelling is what every collector and dashboard is keyed on.
REQUEST_ID_HEADER = "x-request-id"
TRACE_ID_HEADER = "x-trace-id"

MAX_CORRELATION_ID_LENGTH = 128

# Anything outside this set is replaced rather than passed through: control
# characters, quotes, braces and backslashes are what would break a text line or
# a JSON payload, and no legitimate trace id contains them.
_ALLOWED_ID_CHARS = re.compile(r"[^A-Za-z0-9._:\-]")

_request_id: ContextVar[str | None] = ContextVar("observability_request_id", default=None)
_trace_id: ContextVar[str | None] = ContextVar("observability_trace_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("observability_user_id", default=None)


@dataclass(frozen=True)
class LogContext:
    """The correlation values attached to records written in one request."""

    request_id: str | None = None
    trace_id: str | None = None
    user_id: str | None = None

    def as_headers(self, *, request_id_header: str = REQUEST_ID_HEADER) -> dict[str, str]:
        """Return the correlation values as outbound HTTP headers.

        The request id goes out under the platform's header name so the receiving
        service can continue the same chain instead of starting a new one.
        """
        headers: dict[str, str] = {}
        if self.request_id:
            headers[request_id_header] = self.request_id
        if self.trace_id:
            headers[TRACE_ID_HEADER] = self.trace_id
        return headers


@dataclass(frozen=True)
class ContextBinding:
    """The tokens that undo a :func:`set_context_tokens` call.

    Each token is kept with the variable it belongs to, so restoring cannot
    apply a trace-id token to the request-id variable.
    """

    tokens: tuple[tuple[ContextVar[str | None], Token[str | None]], ...] = ()


def new_request_id() -> str:
    """Generate a correlation id for a request that arrived without one."""
    return uuid4().hex


def sanitize_correlation_id(value: str | None) -> str | None:
    """Return a header value safe to embed in a log record, or ``None``.

    Truncates to the length ceiling and replaces every character outside the
    allowed set, so an attacker-controlled header cannot forge a record
    boundary or inject structure into the payload.
    """
    if value is None:
        return None
    cleaned = _ALLOWED_ID_CHARS.sub("-", value.strip())[:MAX_CORRELATION_ID_LENGTH]
    return cleaned or None


def correlation_id_from_headers(headers: Mapping[str, str]) -> str | None:
    """Return the inbound correlation id, sanitized, or ``None`` when absent.

    Header lookups are case-insensitive, and the first header that carries a
    usable value wins.
    """
    lowered = {str(key).casefold(): value for key, value in headers.items()}
    for name in CORRELATION_HEADERS:
        candidate = sanitize_correlation_id(lowered.get(name))
        if candidate:
            return candidate
    return None


def current_context() -> LogContext:
    """Return the correlation context bound to the current execution context."""
    return LogContext(
        request_id=_request_id.get(),
        trace_id=_trace_id.get(),
        user_id=_user_id.get(),
    )


def set_context(
    *,
    request_id: str | None = None,
    trace_id: str | None = None,
    user_id: str | None = None,
) -> LogContext:
    """Bind correlation values to the current context and return them.

    Each value is sanitized, so callers can pass a header value straight
    through. A value left as ``None`` is left unchanged rather than cleared,
    which lets a caller set one field without discarding the rest.
    """
    if request_id is not None:
        _request_id.set(sanitize_correlation_id(request_id) or new_request_id())
    if trace_id is not None:
        _trace_id.set(sanitize_correlation_id(trace_id))
    if user_id is not None:
        _user_id.set(sanitize_correlation_id(user_id))
    return current_context()


def reset_context(binding: ContextBinding) -> None:
    """Restore the values captured by :func:`set_context_tokens`."""
    for variable, token in reversed(binding.tokens):
        variable.reset(token)


def set_context_tokens(
    *,
    request_id: str | None = None,
    trace_id: str | None = None,
    user_id: str | None = None,
) -> ContextBinding:
    """Bind correlation values and return the binding needed to undo it.

    Middleware uses this form: it binds on the way in and restores the previous
    values on the way out, so a request never inherits the previous request's
    identifier when the worker thread is reused.
    """
    tokens: list[tuple[ContextVar[str | None], Token[str | None]]] = []
    if request_id is not None:
        resolved = sanitize_correlation_id(request_id) or new_request_id()
        tokens.append((_request_id, _request_id.set(resolved)))
    if trace_id is not None:
        tokens.append((_trace_id, _trace_id.set(sanitize_correlation_id(trace_id))))
    if user_id is not None:
        tokens.append((_user_id, _user_id.set(sanitize_correlation_id(user_id))))
    return ContextBinding(tuple(tokens))


@contextmanager
def request_scope(
    request_id: str | None = None,
    *,
    trace_id: str | None = None,
    user_id: str | None = None,
) -> Iterator[LogContext]:
    """Bind correlation values for the duration of a block.

    This is the form tests and background jobs use. The previous values are
    restored on exit, so a nested scope cannot leak its identifier.
    """
    binding = set_context_tokens(
        request_id=request_id or new_request_id(),
        trace_id=trace_id,
        user_id=user_id,
    )
    try:
        yield current_context()
    finally:
        reset_context(binding)
