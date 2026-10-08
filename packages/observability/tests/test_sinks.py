"""Tests for the destinations, and above all for the external base class.

The external sink is the extension point a log platform is added through, so the
behaviours that decide whether a deployment survives an outage are pinned here:
a slow platform must not reach a request thread, an unreachable platform must
degrade predictably instead of exhausting memory, and shutdown must not hang.
"""

from __future__ import annotations

import io
import logging
import threading
import time

import pytest

from observability import (
    ExternalSink,
    JsonFormatter,
    SinkConfig,
    create_sink,
    register_sink,
    request_scope,
)
from observability.sinks import available_sinks

pytestmark = pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")


def _record(message: str = "hello", name: str = "app") -> logging.LogRecord:
    return logging.LogRecord(
        name=name,
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )


class _RecordingSink(ExternalSink):
    """A sink that keeps every batch it was asked to deliver."""

    def __init__(self, **options: object) -> None:
        options.setdefault("url", "http://logs.invalid/ingest")
        super().__init__(formatter=JsonFormatter(service_name="s"), options=dict(options))
        self.batches: list[list[dict[str, object]]] = []
        self.sent_event = threading.Event()

    def send(self, records):
        self.batches.append(list(records))
        self.sent_event.set()


class _FailingSink(_RecordingSink):
    """A sink whose transport always fails."""

    def __init__(self, failures: int = 1, **options: object) -> None:
        super().__init__(**options)
        self.remaining_failures = failures
        self.attempts = 0

    def send(self, records):
        self.attempts += 1
        if self.attempts <= self.remaining_failures:
            raise ConnectionError("platform unreachable")


def _wait_for(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_an_external_target_is_added_by_subclassing_and_registering() -> None:
    """Adding a platform is a subclass and a name, not a change to any service."""
    register_sink("recording", lambda *, formatter, options: _RecordingSink(**options))
    try:
        assert "recording" in available_sinks()
        sink = create_sink(SinkConfig("recording"), formatter=JsonFormatter(service_name="s"))
        assert isinstance(sink, _RecordingSink)
    finally:
        from observability.sinks import _SINKS

        _SINKS.pop("recording")


def test_records_are_delivered_in_batches_rather_than_one_at_a_time() -> None:
    sink = _RecordingSink(batch_size=3, flush_interval=0.05)
    sink.startup()
    try:
        for index in range(3):
            sink.emit(_record(f"message {index}"))
        assert _wait_for(lambda: sink.sent_count == 3)
        assert len(sink.batches) == 1
        messages = [record["message"] for record in sink.batches[0]]
        assert messages == ["message 0", "message 1", "message 2"]
    finally:
        sink.shutdown()


def test_a_transient_failure_is_retried_and_the_batch_still_arrives() -> None:
    sink = _FailingSink(failures=1, batch_size=1, flush_interval=0.01, retry_backoff=0.0)
    sink.startup()
    try:
        sink.emit(_record())
        assert _wait_for(lambda: sink.sent_count == 1)
        assert sink.attempts == 2
        assert sink.dropped_count == 0
    finally:
        sink.shutdown()


def test_retries_are_bounded_and_a_lost_batch_is_counted() -> None:
    """An unreachable platform must degrade predictably, not silently."""
    sink = _FailingSink(
        failures=99, batch_size=1, flush_interval=0.01, retry_backoff=0.0, max_retries=2
    )
    sink.startup()
    try:
        sink.emit(_record())
        assert _wait_for(lambda: sink.dropped_count == 1)
        assert sink.attempts == 3
        assert sink.sent_count == 0
    finally:
        sink.shutdown()


def test_a_slow_platform_never_blocks_the_calling_thread() -> None:
    """Backpressure belongs to the queue, not to the request that is logging.

    A request thread must not wait on a network call it made indirectly, so the
    stall is released before shutdown rather than waited out.
    """
    release = threading.Event()
    stalled = threading.Event()

    class _StalledSink(_RecordingSink):
        def send(self, records):
            stalled.set()
            release.wait(timeout=5.0)
            super().send(records)

    sink = _StalledSink(batch_size=5, flush_interval=0.01, max_queue=5)
    sink.startup()
    try:
        started = time.monotonic()
        for index in range(5):
            sink.emit(_record(f"m{index}"))
        elapsed = time.monotonic() - started

        assert elapsed < 0.5, "emit() must not wait for the network"
        assert _wait_for(stalled.is_set)
    finally:
        release.set()
        sink.shutdown()


def test_a_full_queue_drops_the_oldest_and_keeps_the_newest() -> None:
    """During an incident the newest record is the one an operator needs."""
    release = threading.Event()
    started = threading.Event()

    class _BusySink(_RecordingSink):
        def send(self, records):
            started.set()
            release.wait(timeout=5.0)

    sink = _BusySink(batch_size=1, flush_interval=0.01, max_queue=1)
    sink.startup()
    try:
        sink.emit(_record("occupying the worker"))
        assert _wait_for(started.is_set)

        sink.emit(_record("oldest"))
        sink.emit(_record("newest"))
        payload = sink._queue.get_nowait()

        assert payload["message"] == "newest"
        assert sink.dropped_count == 1
    finally:
        release.set()
        sink.shutdown()


def test_shutdown_flushes_within_a_bounded_time() -> None:
    """A slow platform must not hold the process open at exit."""
    sink = _RecordingSink(batch_size=1, flush_interval=0.01, shutdown_timeout=0.2)
    sink.startup()
    sink.emit(_record())

    started = time.monotonic()
    sink.shutdown()
    elapsed = time.monotonic() - started

    assert elapsed < 1.0


def test_a_sink_without_a_url_starts_and_writes_nothing() -> None:
    sink = _RecordingSink(url="")
    sink.startup()
    try:
        sink.emit(_record())
        assert "disabled" in sink.describe()
        assert sink.sent_count == 0
    finally:
        sink.shutdown()


def test_console_sink_writes_a_formatted_line_to_the_stream() -> None:
    from observability.sinks.console import ConsoleSink

    stream = io.StringIO()
    sink = ConsoleSink(formatter=JsonFormatter(service_name="s"), options={"stream": "stdout"})
    sink.stream = stream
    sink.emit(_record("written to the console"))

    assert "written to the console" in stream.getvalue()


def test_file_sink_writes_records_and_reports_its_path(tmp_path) -> None:
    from observability.sinks.file import FileSink

    path = tmp_path / "nested" / "app.log"
    sink = FileSink(formatter=JsonFormatter(service_name="s"), options={"path": str(path)})
    sink.startup()
    try:
        sink.emit(_record("written to the file"))
        sink.flush()
        assert "written to the file" in path.read_text()
        assert str(path) in sink.describe()
    finally:
        sink.shutdown()


def test_file_sink_stays_alive_when_the_path_cannot_be_opened() -> None:
    """A destination that cannot open must not stop the service from serving."""
    from observability.sinks.file import FileSink

    sink = FileSink(
        formatter=JsonFormatter(service_name="s"),
        options={"path": "/proc/definitely-not-writable/app.log"},
    )
    sink.startup()
    try:
        sink.emit(_record("goes nowhere"))
        assert "not writing" in sink.describe()
    finally:
        sink.shutdown()


def test_syslog_sink_flattens_a_multi_line_record_to_one_frame() -> None:
    """Syslog frames are line-based, so a multi-line record would break the stream.

    The text formatter's exception line is the real case: it is genuinely two
    lines, and a collector reading one line per record would see half a record.
    """
    from observability import TextFormatter
    from observability.sinks.syslog import SyslogSink

    sink = SyslogSink(
        formatter=TextFormatter(service_name="s", use_colors=False),
        options={"address": ("127.0.0.1", 514)},
    )
    rendered = sink.format(_record("line one\nline two"))

    assert "\n" not in rendered
    assert "line one | line two" in rendered


def test_every_registered_sink_renders_the_same_field_set(tmp_path, monkeypatch) -> None:
    """One formatter instance behind every destination, so one field set everywhere.

    A dashboard query or an index mapping written against one destination must
    match every other; the field set is assembled once and shared, and this test
    holds each destination to it.
    """
    import json as json_module

    from observability import RECORD_FIELDS, LoggerConfig, configure

    captured: list[dict[str, object]] = []

    class _CapturingSink(ExternalSink):
        def send(self, records):
            captured.extend(records)

    register_sink(
        "capturing",
        lambda *, formatter, options: _CapturingSink(formatter=formatter, options=options),
    )

    log_path = tmp_path / "contract.log"
    configure(
        LoggerConfig(
            service_name="contract",
            format="json",
            sinks=(
                SinkConfig("console", {"stream": "stdout"}),
                SinkConfig("file", {"path": str(log_path)}),
                SinkConfig(
                    "capturing",
                    {"url": "http://logs.invalid/ingest", "batch_size": 1, "flush_interval": 0.01},
                ),
            ),
        )
    )
    monkeypatch.setattr(logging.getLogger().handlers[0], "stream", io.StringIO())

    try:
        with request_scope("req-contract", user_id="user:1"):
            logging.getLogger("contract.test").info(
                "the contract record",
                extra={"event": "contract.test", "status": "ok", "api_key": "sk-secret"},
            )
        _wait_for(lambda: len(captured) == 1)

        console_stream = logging.getLogger().handlers[0].stream.getvalue()
        console_payload = json_module.loads(console_stream.splitlines()[0])
        file_payload = json_module.loads(log_path.read_text().splitlines()[0])
        external_payload = captured[0]

        for name, payload in (
            ("console", console_payload),
            ("file", file_payload),
            ("external", external_payload),
        ):
            # Every contract field is present; call-site extras are additional
            # and are carried through rather than dropped.
            assert set(RECORD_FIELDS) <= set(payload), f"{name} rendered a different field set"
            assert payload["request_id"] == "req-contract", f"{name} lost the correlation id"
            assert payload["api_key"] == "[redacted]", f"{name} shipped an unmasked secret"

        # The three destinations agree field by field, not just in shape.
        assert console_payload == file_payload == external_payload
    finally:
        from observability import shutdown

        shutdown()
        from observability.sinks import _SINKS

        _SINKS.pop("capturing")
