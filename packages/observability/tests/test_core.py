"""Tests for the shared observability package.

Two groups live here. The dependency-health and retry tests are the ones the
four service copies shared verbatim. The logging tests pin the contracts the
consolidation is meant to guarantee: one field set, one formatter behind every
destination, redaction that cannot be bypassed, and a correlation id that
survives from an inbound header to an outbound call.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys

import pytest

from observability import (
    DependencyPolicy,
    DependencyRegistry,
    DependencyStartupError,
    DependencyStatus,
    JsonFormatter,
    LogFormat,
    LoggerConfig,
    RetryPolicy,
    SinkConfig,
    TextFormatter,
    UnknownSinkError,
    available_sinks,
    configure,
    dependency_error_fields,
    get_logger,
    retry_async,
    retry_sync,
    sanitize_exception,
    shutdown,
)


@pytest.fixture(autouse=True)
def _restore_logging():
    """Leave the root logger as the test found it.

    Logging is process-global, and a test that reconfigures it without restoring
    it changes the behaviour of every test that runs after it.
    """
    root = logging.getLogger()
    handlers = list(root.handlers)
    level = root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)
    shutdown()


def _record(**fields: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name=fields.pop("name", "app"),
        level=int(fields.pop("level", logging.INFO)),  # type: ignore[arg-type]
        pathname=__file__,
        lineno=12,
        msg=str(fields.pop("message", "something happened")),
        args=(),
        exc_info=fields.pop("exc_info", None),  # type: ignore[arg-type]
    )
    for key, value in fields.items():
        setattr(record, key, value)
    return record


def test_json_formatter_emits_every_contract_field_and_the_extra_ones() -> None:
    record = _record(
        name="infrastructure.db.startup",
        event="startup.dependency.ok",
        dependency="postgres",
        operation="migrate",
        attempt=2,
        max_attempts=5,
        elapsed_ms=41,
        status="ok",
        error_code="dependency.connection_failed",
    )

    payload = json.loads(JsonFormatter(service_name="agent-service").format(record))

    assert payload["service"] == "agent-service"
    assert payload["event"] == "startup.dependency.ok"
    assert payload["dependency"] == "postgres"
    assert payload["operation"] == "migrate"
    assert payload["message"] == "something happened"
    # Call-site context an operator would otherwise have to read the source to
    # find is carried through, not dropped by the schema.
    assert payload["error_code"] == "dependency.connection_failed"


def test_json_formatter_carries_the_contract_fields_exactly() -> None:
    """A record's key set is the contract, whatever the record happens to carry.

    A field that is present on some documents and absent on others forces a
    mapping change or a query that skips documents, so an unset field is an
    explicit null rather than a missing key.
    """
    from observability import RECORD_FIELDS

    payload = json.loads(JsonFormatter(service_name="agent-service").format(_record()))

    assert set(payload) == set(RECORD_FIELDS)
    assert payload["error"] is None
    assert payload["request_id"] is None


def test_json_formatter_keeps_the_field_order_of_the_contract() -> None:
    """Field order is the render order, so a record reads the same in both formats."""
    from observability import RECORD_FIELDS

    payload = json.loads(JsonFormatter(service_name="agent-service").format(_record()))

    assert tuple(payload) == RECORD_FIELDS


def test_text_formatter_shows_the_operator_fields() -> None:
    record = _record(
        name="app",
        level=logging.ERROR,
        message="tools-service is unavailable during startup connect.",
        event="startup.dependency.failed",
        dependency="tools-service",
        operation="connect",
        attempt=5,
        max_attempts=5,
        status="failed",
        error_code="dependency.connection_failed",
    )

    line = TextFormatter(service_name="agent-service", use_colors=False).format(record)

    assert "agent-service" in line
    assert "event=startup.dependency.failed" in line
    assert "dependency=tools-service" in line
    assert "operation=connect" in line
    assert "attempt=5/5" in line
    assert "status=failed" in line
    assert "error_code=dependency.connection_failed" in line


def test_text_formatter_colors_the_level_only_on_a_terminal(monkeypatch) -> None:
    """A redirected stream or a log file gets no escape codes.

    Escape codes in a shipped log line are noise to a collector and unreadable
    to whoever opens the file, so colour is conditional on a real terminal.
    """
    record = _record(level=logging.ERROR, message="boom")

    monkeypatch.setattr("sys.stdout.isatty", lambda: True, raising=False)
    assert "\x1b[31m" in TextFormatter(service_name="s", use_colors=True).format(record)

    monkeypatch.setattr("sys.stdout.isatty", lambda: False, raising=False)
    assert "\x1b[" not in TextFormatter(service_name="s", use_colors=True).format(record)
    assert "\x1b[" not in TextFormatter(service_name="s", use_colors=False).format(record)


def test_text_formatter_omits_unset_fields() -> None:
    """A text line may drop an unset field, because nothing parses it."""
    line = TextFormatter(service_name="s", use_colors=False, include_source=False).format(_record())

    assert "event=" not in line
    assert "dependency=" not in line


def test_both_formatters_agree_on_the_field_values() -> None:
    """Format identity is a property, not a convention.

    Both renderers call the same builder, so a value cannot appear in one format
    and be missing from the other.
    """
    record = _record(event="order.created", status="ok", request_id="req-1")

    text = TextFormatter(service_name="s", use_colors=False).format(record)
    payload = json.loads(JsonFormatter(service_name="s").format(record))

    assert "event=order.created" in text
    assert "status=ok" in text
    assert payload["event"] == "order.created"
    assert payload["status"] == "ok"


def test_configure_installs_one_handler_per_sink_and_replaces_on_reconfigure() -> None:
    root = logging.getLogger()

    configure(LoggerConfig(service_name="test-service", format=LogFormat.JSON))
    configure(LoggerConfig(service_name="test-service", format=LogFormat.JSON))

    # Configuring twice must replace the handlers, not append to them, or every
    # record is written twice.
    assert root.level == logging.INFO
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, JsonFormatter)
    assert get_logger("app").name == "app"


def test_configure_quiets_named_loggers() -> None:
    httpx_level = logging.getLogger("httpx").level
    try:
        configure(
            LoggerConfig(
                service_name="test-service",
                format=LogFormat.TEXT,
                quiet_loggers=("httpx",),
            )
        )

        assert logging.getLogger("httpx").level == logging.WARNING
    finally:
        logging.getLogger("httpx").setLevel(httpx_level)


def test_every_configured_sink_shares_one_formatter_instance() -> None:
    """Two destinations cannot disagree about a record, because neither owns it."""
    configure(
        LoggerConfig(
            service_name="test-service",
            format=LogFormat.JSON,
            sinks=(
                SinkConfig("console", {"stream": "stdout"}),
                SinkConfig("console", {"stream": "stderr"}),
            ),
        )
    )

    formatters = {handler.formatter for handler in logging.getLogger().handlers}

    assert len(formatters) == 1
    assert isinstance(next(iter(formatters)), JsonFormatter)


def test_configure_honours_the_configured_level() -> None:
    configure(LoggerConfig(service_name="test-service", level="WARNING"))

    assert logging.getLogger().level == logging.WARNING


def test_unknown_sink_name_fails_at_configuration_time() -> None:
    """A typo in a destination name must not silently discard every record."""
    with pytest.raises(UnknownSinkError) as exc_info:
        configure(
        LoggerConfig(service_name="test-service", sinks=(SinkConfig("logstash"),))
    )

    assert "logstash" in str(exc_info.value)
    assert "console" in str(exc_info.value)


def test_the_shipped_destinations_are_registered() -> None:
    """console, file, syslog, the Elasticsearch target, and the external base class."""
    assert set(available_sinks()) == {"console", "elasticsearch", "file", "syslog", "external"}


def test_sensitive_keys_are_masked_in_both_formats() -> None:
    """Redaction lives in the formatter, so a call site cannot forget it."""
    record = _record(
        message="upstream rejected the key", api_key="sk-live-abcdef", password="hunter2"
    )

    payload = json.loads(JsonFormatter(service_name="s").format(record))
    line = TextFormatter(service_name="s", use_colors=False).format(record)

    assert payload["api_key"] == "[redacted]"
    assert payload["password"] == "[redacted]"
    assert "sk-live-abcdef" not in line
    assert "hunter2" not in line


def test_an_exception_is_reported_as_structure_rather_than_a_rendered_traceback() -> None:
    try:
        raise ConnectionError("postgres://user:hunter2@db:5432/x down")
    except ConnectionError:
        record = _record(message="db unavailable", exc_info=sys.exc_info())

    payload = json.loads(JsonFormatter(service_name="s").format(record))

    assert payload["error"]["exception_type"] == "ConnectionError"
    assert "hunter2" not in json.dumps(payload)


def test_correlation_from_the_context_reaches_a_record_without_a_call_site_passing_it() -> None:
    from observability import request_scope

    with request_scope("req-123", user_id="user:abc"):
        payload = json.loads(JsonFormatter(service_name="s").format(_record()))

    assert payload["request_id"] == "req-123"
    assert payload["user_id"] == "user:abc"


def test_an_explicit_value_on_the_record_wins_over_the_ambient_context() -> None:
    """A call site that knows better says so, rather than being overruled."""
    from observability import request_scope

    with request_scope("ambient"):
        payload = json.loads(JsonFormatter(service_name="s").format(_record(request_id="explicit")))

    assert payload["request_id"] == "explicit"


def test_an_inbound_correlation_header_survives_sanitisation() -> None:
    from observability import correlation_id_from_headers

    assert correlation_id_from_headers({"X-Request-ID": "abc-123"}) == "abc-123"
    # A caller cannot inject a newline that would forge a second log record.
    assert correlation_id_from_headers({"x-request-id": "abc\n\nforged"}) == "abc--forged"
    assert correlation_id_from_headers({}) is None


def test_the_context_is_restored_when_a_scope_exits() -> None:
    from observability import current_context, request_scope

    with request_scope("outer"):
        with request_scope("inner"):
            assert current_context().request_id == "inner"
        assert current_context().request_id == "outer"


def test_sanitize_exception_redacts_credentials_from_messages() -> None:
    exc = RuntimeError(
        "failed postgresql://user:secret@localhost:5432/agent with token=abc123 and password=top"
    )

    fields = sanitize_exception(exc)

    assert fields["exception_type"] == "RuntimeError"
    assert "secret" not in fields["exception_message"]
    assert "abc123" not in fields["exception_message"]
    assert "top" not in fields["exception_message"]
    assert "[redacted]" in fields["exception_message"]


def test_dependency_error_fields_hide_python_exception_details() -> None:
    exc = RuntimeError(
        "asyncpg.exceptions.CannotConnectNowError: failed postgresql://user:secret@db/agent"
    )

    fields = dependency_error_fields(exc, dependency="postgres")

    assert fields == {
        "error_code": "dependency.unavailable",
        "error_summary": "postgres is unavailable.",
        "remediation": "Check that the dependency is running and reachable from the service.",
        "retryable": False,
    }
    assert "RuntimeError" not in fields.values()
    assert "asyncpg" not in fields.values()


def test_retry_async_retries_transient_failures_without_sleeping() -> None:
    attempts = 0

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionError("connection refused")
        return "ok"

    result = asyncio.run(
        retry_async(
            operation,
            operation_name="connect",
            dependency="postgres",
            policy=RetryPolicy(attempts=3, initial_delay_seconds=0, jitter=False),
        )
    )

    assert result == "ok"
    assert attempts == 3


def test_retry_async_logs_operator_message_without_exception_type() -> None:
    records: list[dict] = []

    class FakeLogger:
        def warning(self, message: str, *, extra: dict) -> None:
            records.append({"message": message, "extra": extra})

    attempts = 0

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConnectionError("asyncpg connection refused")
        return "ok"

    asyncio.run(
        retry_async(
            operation,
            operation_name="connect",
            dependency="postgres",
            policy=RetryPolicy(attempts=2, initial_delay_seconds=0, jitter=False),
            logger=FakeLogger(),
        )
    )

    assert records[0]["message"] == "postgres is unavailable; retrying startup connect."
    assert records[0]["extra"]["error_code"] == "dependency.connection_failed"
    assert "exception_type" not in records[0]["extra"]
    assert "asyncpg" not in records[0]["extra"].values()


def test_retry_async_raises_clear_dependency_error_after_exhaustion() -> None:
    async def operation() -> str:
        raise ConnectionError("asyncpg.exceptions.CannotConnectNowError: connection refused")

    with pytest.raises(DependencyStartupError) as exc_info:
        asyncio.run(
            retry_async(
                operation,
                operation_name="connect",
                dependency="postgres",
                policy=RetryPolicy(attempts=1, initial_delay_seconds=0, jitter=False),
            )
        )

    message = str(exc_info.value)
    assert message == (
        "postgres is unavailable during startup connect. "
        "Check that the dependency is running and reachable from the service."
    )
    assert "asyncpg" not in message
    assert "ConnectionError" not in message


def test_retry_sync_retries_transient_failures_without_sleeping() -> None:
    attempts = 0

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionError("connection refused")
        return "ok"

    result = retry_sync(
        operation,
        operation_name="migrate",
        dependency="postgres",
        policy=RetryPolicy(attempts=3, initial_delay_seconds=0, jitter=False),
    )

    assert result == "ok"
    assert attempts == 3


def test_retry_policy_for_dependency_resolves_from_the_shared_policy_file() -> None:
    """Startup retries read configs/resilience.yaml like the HTTP retries do.

    postgres and redis carry explicit startup sections (a process coming up can
    wait longer per attempt than a request path); anything without a section
    falls back to the shared defaults.
    """
    startup = RetryPolicy.for_dependency("postgres")
    assert (startup.attempts, startup.initial_delay_seconds, startup.max_delay_seconds) == (
        5,
        0.5,
        8.0,
    )
    assert startup.jitter is True

    redis = RetryPolicy.for_dependency("redis")
    assert redis.attempts == 5

    fallback = RetryPolicy.for_dependency("dependency-without-a-section")
    assert (fallback.attempts, fallback.initial_delay_seconds, fallback.max_delay_seconds) == (
        3,
        0.2,
        2.0,
    )


def test_dependency_registry_tracks_required_and_degraded_states() -> None:
    registry = DependencyRegistry()
    registry.record_ok("postgres", policy=DependencyPolicy.REQUIRED)
    registry.record_degraded("neo4j", hint="Graph features disabled.")

    assert registry.ready() is True
    snapshot = registry.snapshot()
    assert snapshot["postgres"].status == "ok"
    assert snapshot["postgres"].ready is True
    assert snapshot["neo4j"].status == "degraded"
    assert snapshot["neo4j"].ready is True


def test_dependency_registry_not_ready_when_required_dependency_fails() -> None:
    registry = DependencyRegistry()
    registry.record(
        DependencyStatus(
            name="postgres",
            policy=DependencyPolicy.REQUIRED,
            status="failed",
        )
    )

    assert registry.ready() is False
    assert registry.snapshot()["postgres"].ready is False


def test_dependency_registry_is_not_ready_before_anything_is_recorded() -> None:
    """An empty registry must not report a green readiness.

    ``all([])`` is True, so the pre-consolidation copies reported ready before
    any dependency had been checked - a green readiness over a dependency map
    nobody had ever filled in.
    """
    assert DependencyRegistry().ready() is False


def test_readiness_payload_reports_not_ready_for_an_empty_registry() -> None:
    from observability import readiness_payload

    payload = readiness_payload(DependencyRegistry(), service_name="test-service")

    assert payload["status"] == "not_ready"
    assert payload["service"] == "test-service"
    assert payload["dependencies"] == {}
