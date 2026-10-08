"""The middleware that gives every record in one request the same correlation id.

A service sets the correlation values once, here, and every log line written
while handling the request carries them. The middleware is plain ASGI, so the
same class serves FastAPI services and the FastMCP server, and the package stays
free of framework knowledge.

An inbound correlation header is preserved so the identifier matches the edge and
any service upstream; when it is absent one is generated. The same value is
written onto the response, so an operator can take an identifier from a response
and find every record the request produced.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping
from typing import Any

from .context import (
    REQUEST_ID_HEADER,
    correlation_id_from_headers,
    new_request_id,
    reset_context,
    sanitize_correlation_id,
    set_context_tokens,
)

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]


def _header_value(raw_headers: Iterable[tuple[bytes, bytes]], name: str) -> str | None:
    """Return the first value of a header, decoded, or ``None``."""
    lowered = name.encode("latin-1").lower()
    for key, value in raw_headers:
        if key.lower() == lowered:
            return value.decode("latin-1", errors="replace")
    return None


class CorrelationMiddleware:
    """Bind the correlation context for the lifetime of one request.

    The values are bound with tokens and restored on the way out, so a worker
    that handles the next request never inherits this request's identifier.
    """

    def __init__(self, app: Any, *, request_id_header: str = REQUEST_ID_HEADER) -> None:
        self.app = app
        self._request_id_header = request_id_header.lower()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        raw_headers = scope.get("headers") or ()
        header_map = {key.decode("latin-1"): value.decode("latin-1") for key, value in raw_headers}
        inbound = correlation_id_from_headers(header_map)
        request_id = inbound or new_request_id()
        trace_id = sanitize_correlation_id(_header_value(raw_headers, "x-trace-id"))

        binding = set_context_tokens(request_id=request_id, trace_id=trace_id)
        try:
            await self._traced(scope, receive, send, request_id, header_map)
        finally:
            reset_context(binding)

    async def _traced(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        request_id: str,
        header_map: Mapping[str, str],
    ) -> None:
        """Run the request inside a server span when telemetry is on.

        The span continues an upstream trace when the request carries a
        ``traceparent``, and the trace id it produces is bound into the log
        context, so the trace in a tracing UI and the records in a log stream are
        joined by one value. With telemetry off this is a plain call through.
        """
        from .otel import current_trace_id, extract_context, is_enabled, tracer

        if not is_enabled():
            await self.app(scope, receive, self._send_with_header(send, request_id))
            return

        from opentelemetry.trace import SpanKind, Status, StatusCode

        attributes = {
            "http.request.method": scope.get("method", "GET"),
            "url.path": scope.get("path", ""),
            "platform.request_id": request_id,
        }
        with tracer().start_as_current_span(
            f"{scope.get('method', 'GET')} {scope.get('path', '')}",
            context=extract_context(header_map),
            kind=SpanKind.SERVER,
            attributes=attributes,
            record_exception=False,
        ) as span:
            # The span may have continued an upstream trace; the log records
            # should carry the trace the span actually belongs to. The value is
            # bound with a token and restored when the span ends, so it cannot
            # leak into the next request handled by the same worker.
            from .context import reset_context, set_context_tokens

            trace_id = current_trace_id()
            trace_binding = set_context_tokens(trace_id=trace_id) if trace_id else None
            try:
                await self.app(scope, receive, self._send_with_header(send, request_id))
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise
            finally:
                if trace_binding is not None:
                    reset_context(trace_binding)

    def _send_with_header(self, send: Send, request_id: str) -> Send:
        """Wrap ``send`` so the response carries the correlation id back."""

        async def wrapped(message: Mapping[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                headers.append(
                    (self._request_id_header.encode("latin-1"), request_id.encode("latin-1"))
                )
                message = {**message, "headers": headers}
            await send(dict(message))

        return wrapped
