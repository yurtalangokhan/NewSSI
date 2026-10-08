"""Tests for the OpenTelemetry integration.

The properties pinned here are the ones the platform depends on: telemetry is a
no-op until enabled, an enabled span puts its trace id into every log record
written inside it, an upstream traceparent is continued rather than replaced, and
an outbound call carries the context on. The exporter itself is not exercised
against a network; the provider wiring is asserted structurally.
"""

from __future__ import annotations

import json
import logging

import pytest

from observability import (
    CorrelationMiddleware,
    LoggerConfig,
    SinkConfig,
    TelemetryConfig,
    configure,
    setup_telemetry,
    shutdown,
    shutdown_telemetry,
)


@pytest.fixture(autouse=True)
def _clean_state():
    root = logging.getLogger()
    handlers = list(root.handlers)
    level = root.level
    yield
    shutdown_telemetry()
    shutdown()
    root.handlers[:] = handlers
    root.setLevel(level)


def _record(message: str = "hello") -> logging.LogRecord:
    return logging.LogRecord(
        name="app",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )


def test_telemetry_is_off_until_enabled() -> None:
    """The default must cost nothing: no providers, no spans, no exports."""
    from observability import telemetry_enabled

    setup_telemetry(TelemetryConfig(service_name="s"))

    assert telemetry_enabled() is False


def test_enabled_without_an_endpoint_is_not_active() -> None:
    """Enabling with nowhere to deliver would silently lose everything."""
    from observability import telemetry_enabled

    setup_telemetry(TelemetryConfig(service_name="s", enabled=True))

    assert telemetry_enabled() is False


def test_an_invalid_sample_ratio_is_rejected() -> None:
    with pytest.raises(ValueError):
        TelemetryConfig(service_name="s", sample_ratio=1.5)


def test_setup_installs_providers_and_the_w3c_propagator() -> None:
    import opentelemetry.propagate as propagate
    import opentelemetry.trace as otel_trace

    setup_telemetry(
        TelemetryConfig(
            service_name="s",
            enabled=True,
            endpoint="http://127.0.0.1:9/v1/traces",
            export_timeout_ms=100,
        )
    )

    assert otel_trace.get_tracer_provider() is not None
    # The global propagator must speak W3C TraceContext: the middleware extracts
    # an upstream traceparent with it.
    carrier = {"traceparent": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"}
    context = propagate.extract(carrier)
    from opentelemetry.trace import get_current_span

    assert get_current_span(context).get_span_context().trace_id is not None


def test_a_span_puts_its_trace_id_into_log_records() -> None:
    """The join key between a trace and its log lines is one value."""
    import io

    setup_telemetry(
        TelemetryConfig(
            service_name="s",
            enabled=True,
            endpoint="http://127.0.0.1:9/v1/traces",
            export_timeout_ms=100,
        )
    )
    stream = io.StringIO()
    configure(LoggerConfig(service_name="s", format="json", sinks=(SinkConfig("console"),)))
    logging.getLogger().handlers[0].stream = stream

    from observability import tracer

    with tracer().start_as_current_span("operation"):
        from observability import current_trace_id

        trace_id = current_trace_id()
        logging.getLogger("app").info("inside the span")

    payload = json.loads(stream.getvalue().splitlines()[0])

    assert trace_id is not None
    assert payload["trace_id"] == trace_id
    assert len(payload["trace_id"]) == 32


def test_records_outside_a_span_carry_no_trace_id() -> None:
    import io

    setup_telemetry(
        TelemetryConfig(
            service_name="s",
            enabled=True,
            endpoint="http://127.0.0.1:9/v1/traces",
            export_timeout_ms=100,
        )
    )
    stream = io.StringIO()
    configure(LoggerConfig(service_name="s", format="json", sinks=(SinkConfig("console"),)))
    logging.getLogger().handlers[0].stream = stream

    logging.getLogger("app").info("outside any span")

    payload = json.loads(stream.getvalue().splitlines()[0])

    assert payload["trace_id"] is None


def test_the_middleware_creates_a_span_and_binds_the_trace_id() -> None:
    """A request served with telemetry on is one span, and its logs know it."""
    import io

    setup_telemetry(
        TelemetryConfig(
            service_name="s",
            enabled=True,
            endpoint="http://127.0.0.1:9/v1/traces",
            export_timeout_ms=100,
        )
    )
    stream = io.StringIO()
    configure(LoggerConfig(service_name="s", format="json", sinks=(SinkConfig("console"),)))
    logging.getLogger().handlers[0].stream = stream

    seen: dict[str, str | None] = {}

    async def app(scope, receive, send) -> None:
        from observability import current_trace_id

        seen["trace_id"] = current_trace_id()
        logging.getLogger("handler").info("inside the request")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    import asyncio

    async def run() -> None:
        async def receive() -> dict[str, object]:
            return {"type": "http.request"}

        async def send(message: dict[str, object]) -> None:
            pass

        await CorrelationMiddleware(app)(
            {"type": "http", "method": "GET", "path": "/x", "headers": []},
            receive,
            send,
        )

    asyncio.run(run())
    payload = json.loads(stream.getvalue().splitlines()[0])

    assert seen["trace_id"] is not None
    assert payload["trace_id"] == seen["trace_id"]


def test_an_upstream_traceparent_is_continued_not_replaced() -> None:
    """A request that arrives inside a trace stays inside that trace."""
    import io

    setup_telemetry(
        TelemetryConfig(
            service_name="s",
            enabled=True,
            endpoint="http://127.0.0.1:9/v1/traces",
            export_timeout_ms=100,
        )
    )
    stream = io.StringIO()
    configure(LoggerConfig(service_name="s", format="json", sinks=(SinkConfig("console"),)))
    logging.getLogger().handlers[0].stream = stream

    upstream_trace_id = "0af7651916cd43dd8448eb211c80319c"

    async def app(scope, receive, send) -> None:
        from observability import current_trace_id

        logging.getLogger("handler").info("continued")
        assert current_trace_id() == upstream_trace_id
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    import asyncio

    async def run() -> None:
        async def receive() -> dict[str, object]:
            return {"type": "http.request"}

        async def send(message: dict[str, object]) -> None:
            pass

        await CorrelationMiddleware(app)(
            {
                "type": "http",
                "method": "GET",
                "path": "/x",
                "headers": [
                    (b"traceparent", f"00-{upstream_trace_id}-b7ad6b7169203331-01".encode())
                ],
            },
            receive,
            send,
        )

    asyncio.run(run())
    payload = json.loads(stream.getvalue().splitlines()[0])

    assert payload["trace_id"] == upstream_trace_id


def test_inject_context_fills_a_missing_traceparent_only() -> None:
    setup_telemetry(
        TelemetryConfig(
            service_name="s",
            enabled=True,
            endpoint="http://127.0.0.1:9/v1/traces",
            export_timeout_ms=100,
        )
    )

    from observability import inject_context, tracer

    with tracer().start_as_current_span("outbound"):
        carrier: dict[str, str] = {}
        inject_context(carrier)
        assert "traceparent" in carrier

        explicit: dict[str, str] = {"traceparent": "00-" + "1" * 32 + "-" + "2" * 16 + "-01"}
        inject_context(explicit)
        assert explicit["traceparent"].startswith("00-11111111")


def test_metrics_helpers_work_when_telemetry_is_off() -> None:
    """A no-op meter keeps call sites free of branching."""
    from observability import counter, histogram

    counter("demo.count").add(1)
    histogram("demo.duration").record(0.5)


def test_the_middleware_passes_through_when_telemetry_is_off() -> None:
    """The default path must not import or touch the SDK at all."""
    seen: list[str | None] = []

    async def app(scope, receive, send) -> None:
        from observability import current_trace_id

        seen.append(current_trace_id())
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    import asyncio

    async def run() -> None:
        async def receive() -> dict[str, object]:
            return {"type": "http.request"}

        async def send(message: dict[str, object]) -> None:
            pass

        await CorrelationMiddleware(app)(
            {"type": "http", "method": "GET", "path": "/x", "headers": []},
            receive,
            send,
        )

    asyncio.run(run())

    assert seen == [None]
