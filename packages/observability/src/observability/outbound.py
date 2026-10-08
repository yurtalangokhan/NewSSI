"""Correlation headers for outbound HTTP calls.

A request's identifier should not stop at the service boundary: when this
service calls another one, the same identifier goes with the call, so one
request is one chain across every service it touches and every log stream
involved.

httpx has no global hook registry, so the hooks here are attached where a client
is constructed:

```python
client = httpx.AsyncClient(..., event_hooks=correlation_event_hooks())
```

Inside a request the hooks add the current correlation headers; outside one they
add nothing, so a background job's call starts a fresh chain rather than logging
under a stale identifier. A caller's explicit header always wins, because the
hook only fills what is missing.
"""

from __future__ import annotations

from typing import Any

from .context import current_context


def outbound_headers() -> dict[str, str]:
    """Return the correlation headers for an outbound HTTP call.

    Empty outside a request scope: the receiving service then starts a new chain
    instead of logging under an identifier that no longer means anything.
    """
    return current_context().as_headers()


def _fill(request: Any) -> None:
    """Add the correlation headers a request does not already carry.

    Only what is missing is filled: a call site that deliberately set its own
    correlation id is not overruled, and httpx's ``update`` would overwrite it.
    The W3C ``traceparent`` is injected the same way when telemetry is on, so an
    outbound call continues the span the request is being served in.
    """
    for name, value in outbound_headers().items():
        if name not in request.headers:
            request.headers[name] = value
    from .otel import TRACEPARENT_HEADER, inject_context

    inject_context(request.headers)
    # inject_context writes the W3C canonical lowercase name; httpx headers are
    # case-insensitive, but the explicit check above used the constant, so make
    # sure a caller-set traceparent under any spelling is still respected.
    if TRACEPARENT_HEADER in request.headers and "traceparent" not in request.headers:
        request.headers["traceparent"] = request.headers[TRACEPARENT_HEADER]


async def async_request_hook(request: Any) -> None:
    """httpx request hook for ``AsyncClient``: fill the correlation headers."""
    _fill(request)


def sync_request_hook(request: Any) -> None:
    """httpx request hook for the sync ``Client``: fill the correlation headers."""
    _fill(request)


def correlation_event_hooks() -> dict[str, list[Any]]:
    """The event-hooks mapping for an ``httpx.AsyncClient``."""
    return {"request": [async_request_hook]}


def correlation_sync_event_hooks() -> dict[str, list[Any]]:
    """The event-hooks mapping for the sync ``httpx.Client``."""
    return {"request": [sync_request_hook]}
