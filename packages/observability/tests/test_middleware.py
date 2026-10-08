"""Tests for the correlation middleware and outbound propagation.

These pin the behaviours the field contract depends on: an inbound identifier is
preserved, an absent one is generated, a hostile header cannot forge records, the
context does not leak between requests, and the identifier travels out again.
"""

from __future__ import annotations

import json
import logging

import pytest

from observability import (
    CorrelationMiddleware,
    LoggerConfig,
    SinkConfig,
    outbound_headers,
    request_scope,
)
from observability.context import current_context


@pytest.fixture(autouse=True)
def _clean_logging():
    root = logging.getLogger()
    handlers = list(root.handlers)
    level = root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)
    from observability import shutdown

    shutdown()


class _Responder:
    """A minimal ASGI app that records the context it ran under."""

    def __init__(self) -> None:
        self.seen: list[dict[str, str | None]] = []

    async def __call__(self, scope, receive, send) -> None:
        self.seen.append(
            {
                "request_id": current_context().request_id,
                "trace_id": current_context().trace_id,
            }
        )
        start = {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/plain")],
        }
        await send(start)
        await send({"type": "http.response.body", "body": b"ok"})


def _scope(headers: list[tuple[bytes, bytes]] | None = None) -> dict[str, object]:
    return {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers or [],
    }


async def _call(app, scope) -> list[dict[str, object]]:
    """Run one request through the middleware and collect the sent messages."""
    sent: list[dict[str, object]] = []

    async def receive() -> dict[str, object]:
        return {"type": "http.request"}

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    await app(scope, receive, send)
    return sent


def test_an_inbound_request_id_is_preserved() -> None:
    """The identifier the edge chose is the identifier the service logs under."""
    responder = _Responder()
    app = CorrelationMiddleware(responder)

    sent = _run(_call(app, _scope([(b"x-request-id", b"edge-123")])))
    assert responder.seen[0]["request_id"] == "edge-123"
    response_headers = dict(sent[0]["headers"])  # type: ignore[arg-type]
    assert response_headers[b"x-request-id"] == b"edge-123"


def test_a_missing_request_id_is_generated_and_returned() -> None:
    responder = _Responder()
    app = CorrelationMiddleware(responder)

    sent = _run(_call(app, _scope()))
    generated = responder.seen[0]["request_id"]
    assert generated
    assert dict(sent[0]["headers"])[b"x-request-id"].decode() == generated  # type: ignore[arg-type]


def test_a_hostile_header_cannot_inject_a_record_boundary() -> None:
    """A newline in the header would forge a second log record downstream."""
    responder = _Responder()
    app = CorrelationMiddleware(responder)

    _run(_call(app, _scope([(b"x-request-id", b"abc\nINJECTED: true")])))
    bound = responder.seen[0]["request_id"]
    assert bound == "abc-INJECTED:-true"
    # The property that matters: no record boundary survives the filter.
    assert "\n" not in bound


def test_the_context_does_not_leak_between_requests() -> None:
    """A worker that handles the next request must not inherit the last id."""
    responder = _Responder()
    app = CorrelationMiddleware(responder)

    _run(_call(app, _scope([(b"x-request-id", b"first")])))
    _run(_call(app, _scope()))

    assert responder.seen[0]["request_id"] == "first"
    assert responder.seen[1]["request_id"] != "first"
    assert current_context().request_id is None


def test_records_written_during_the_request_carry_the_id() -> None:
    """The whole point: a log line written anywhere in the handler is correlated."""
    import io

    stream = io.StringIO()
    from observability import configure

    configure(
        LoggerConfig(
            service_name="s",
            format="json",
            sinks=(SinkConfig("console", {"stream": "stdout"}),),
        )
    )
    logging.getLogger().handlers[0].stream = stream

    async def logging_app(scope, receive, send) -> None:
        logging.getLogger("handler").info("inside the request")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    _run(_call(CorrelationMiddleware(logging_app), _scope([(b"x-request-id", b"req-9")])))
    payload = json.loads(stream.getvalue().splitlines()[0])

    assert payload["request_id"] == "req-9"


def test_outbound_headers_continue_the_chain() -> None:
    """A call made inside a request carries the id; one outside carries nothing."""
    with request_scope("req-out"):
        headers = outbound_headers()

    assert headers["x-request-id"] == "req-out"
    assert outbound_headers() == {}


def test_a_non_http_scope_passes_through_untouched() -> None:
    """Lifespan and other protocols have no headers to correlate."""
    responder = _Responder()
    app = CorrelationMiddleware(responder)

    _run(_call(app, {"type": "lifespan"}))

    # Passed through untouched: no correlation values were bound for a protocol
    # that has no headers to correlate.
    assert responder.seen == [{"request_id": None, "trace_id": None}]


def _run(awaitable):
    import asyncio

    return asyncio.run(awaitable)
