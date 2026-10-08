"""Pure-ASGI middleware recording request count, latency and server errors."""

import time
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from .registry import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUEST_ERRORS_TOTAL,
    HTTP_REQUESTS_TOTAL,
)

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

#: Label value used when no route matched, so 404 scans and probe traffic cannot
#: create one time series per URL they happen to try.
UNMATCHED_ROUTE = "__unmatched__"

#: Label value used for any HTTP method outside the known set below.
UNKNOWN_METHOD = "__unknown__"

#: scope["method"] is set by the ASGI server straight from the raw request
#: line, before routing runs -- RFC 7230's method token grammar allows
#: almost any non-whitespace ASCII, so an unbounded label here is the same
#: cardinality hole UNMATCHED_ROUTE exists to close for paths, just on the
#: method instead.
_KNOWN_METHODS = frozenset(
    {"GET", "HEAD", "POST", "PUT", "DELETE", "CONNECT", "OPTIONS", "TRACE", "PATCH"}
)


class MetricsMiddleware:
    """Record inbound HTTP traffic against the shared Prometheus registry.

    The matched route template is read from ``scope["route"]`` *after* the inner
    application has run — Starlette's router writes it there during dispatch —
    so labels stay bounded regardless of how many distinct URLs are requested.
    Requests to ``metrics_path`` are passed through unrecorded, keeping the
    scrape itself out of the numbers it reports.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        service_name: str,
        metrics_path: str = "/metrics",
    ) -> None:
        self.app = app
        self.service_name = service_name
        self.metrics_path = metrics_path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") == self.metrics_path:
            await self.app(scope, receive, send)
            return

        method = _method_label(scope)
        status_code = 500
        started = time.perf_counter()

        async def send_wrapper(message: MutableMapping[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.perf_counter() - started
            labels = {
                "service": self.service_name,
                "method": method,
                "route": _route_template(scope),
            }
            status = str(status_code)

            HTTP_REQUESTS_TOTAL.labels(**labels, status=status).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(**labels).observe(duration)
            if status_code >= 500:
                HTTP_REQUEST_ERRORS_TOTAL.labels(**labels, status=status).inc()


def _method_label(scope: Scope) -> str:
    """Return the HTTP method label, bounded to the known method set."""
    method = scope.get("method", "GET")
    if not isinstance(method, str):
        return UNKNOWN_METHOD
    upper = method.upper()
    return upper if upper in _KNOWN_METHODS else UNKNOWN_METHOD


def _route_template(scope: Scope) -> str:
    """Return the matched route template, or a single bucket for unmatched URLs."""
    route = scope.get("route")
    template = getattr(route, "path", None)
    if not isinstance(template, str) or not template:
        return UNMATCHED_ROUTE
    return f"{scope.get('root_path', '')}{template}"


__all__ = ["UNKNOWN_METHOD", "UNMATCHED_ROUTE", "MetricsMiddleware"]
