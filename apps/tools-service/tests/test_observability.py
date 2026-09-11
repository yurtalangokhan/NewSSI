from __future__ import annotations

import json
import logging

import pytest


def test_json_log_formatter_emits_service_event_and_extra_fields() -> None:
    from src.core.observability import JsonLogFormatter

    record = logging.LogRecord(
        name="src.core.database",
        level=logging.INFO,
        pathname=__file__,
        lineno=12,
        msg="Postgres migrations completed.",
        args=(),
        exc_info=None,
    )
    record.service = "tools-service"
    record.event = "startup.dependency.ok"
    record.dependency = "postgres"
    record.operation = "connect"
    record.attempt = 2
    record.max_attempts = 5
    record.elapsed_ms = 41
    record.status = "ok"

    payload = json.loads(JsonLogFormatter(service_name="tools-service").format(record))

    assert payload["service"] == "tools-service"
    assert payload["event"] == "startup.dependency.ok"
    assert payload["dependency"] == "postgres"
    assert payload["operation"] == "connect"
    assert payload["attempt"] == 2
    assert payload["max_attempts"] == 5
    assert payload["elapsed_ms"] == 41
    assert payload["status"] == "ok"
    assert payload["message"] == "Postgres migrations completed."


def test_text_log_formatter_uses_color_and_operator_fields() -> None:
    from src.core.observability import TextLogFormatter

    record = logging.LogRecord(
        name="src.core.database",
        level=logging.ERROR,
        pathname=__file__,
        lineno=12,
        msg="postgres is unavailable during startup connect.",
        args=(),
        exc_info=None,
    )
    record.event = "startup.dependency.failed"
    record.dependency = "postgres"
    record.operation = "connect"
    record.attempt = 5
    record.max_attempts = 5
    record.status = "failed"
    record.error_code = "dependency.connection_failed"

    line = TextLogFormatter(service_name="tools-service").format(record)

    assert "\x1b[31mERROR\x1b[0m" in line
    assert "\x1b[31mfailed\x1b[0m" in line
    assert "tools-service" in line
    assert "event=startup.dependency.failed" in line
    assert "dependency=postgres" in line
    assert "operation=connect" in line
    assert "attempt=5/5" in line
    assert "error_code=dependency.connection_failed" in line


def test_configure_logging_installs_single_service_formatter() -> None:
    from src.core.observability import configure_logging, get_logger

    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    try:
        configure_logging(service_name="tools-service", log_level="INFO", log_format="json")
        configure_logging(service_name="tools-service", log_level="INFO", log_format="json")

        logger = get_logger("src.core.database")

        assert logger.name == "src.core.database"
        assert root.level == logging.INFO
        assert len(root.handlers) == 1
        assert root.handlers[0].formatter.__class__.__name__ == "JsonLogFormatter"
    finally:
        root.handlers[:] = original_handlers
        root.setLevel(original_level)


def test_sanitize_exception_redacts_credentials_from_messages() -> None:
    from src.core.observability import sanitize_exception

    exc = RuntimeError(
        "failed postgresql://user:secret@localhost:5432/tools with token=abc123 and password=top"
    )

    fields = sanitize_exception(exc)

    assert fields["exception_type"] == "RuntimeError"
    assert "secret" not in fields["exception_message"]
    assert "abc123" not in fields["exception_message"]
    assert "top" not in fields["exception_message"]
    assert "[redacted]" in fields["exception_message"]


def test_dependency_error_fields_hide_python_exception_details() -> None:
    from src.core.observability import dependency_error_fields

    exc = RuntimeError(
        "asyncpg.exceptions.CannotConnectNowError: failed postgresql://user:secret@db/tools"
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


@pytest.mark.asyncio
async def test_retry_async_retries_transient_failures_without_sleeping() -> None:
    from src.core.observability import RetryPolicy, retry_async

    attempts = 0

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionError("connection refused")
        return "ok"

    result = await retry_async(
        operation,
        operation_name="connect",
        dependency="postgres",
        policy=RetryPolicy(attempts=3, initial_delay_seconds=0, jitter=False),
    )

    assert result == "ok"
    assert attempts == 3


@pytest.mark.asyncio
async def test_retry_async_logs_operator_message_without_exception_type() -> None:
    from src.core.observability import RetryPolicy, retry_async

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

    await retry_async(
        operation,
        operation_name="connect",
        dependency="postgres",
        policy=RetryPolicy(attempts=2, initial_delay_seconds=0, jitter=False),
        logger=FakeLogger(),
    )

    assert records[0]["message"] == "postgres is unavailable; retrying startup connect."
    assert records[0]["extra"]["error_code"] == "dependency.connection_failed"
    assert "exception_type" not in records[0]["extra"]
    assert "asyncpg" not in records[0]["extra"].values()


@pytest.mark.asyncio
async def test_retry_async_raises_clear_dependency_error_after_exhaustion() -> None:
    from src.core.observability import DependencyStartupError, RetryPolicy, retry_async

    async def operation() -> str:
        raise ConnectionError("asyncpg.exceptions.CannotConnectNowError: connection refused")

    with pytest.raises(DependencyStartupError) as exc_info:
        await retry_async(
            operation,
            operation_name="connect",
            dependency="postgres",
            policy=RetryPolicy(attempts=1, initial_delay_seconds=0, jitter=False),
        )

    message = str(exc_info.value)
    assert message == (
        "postgres is unavailable during startup connect. "
        "Check that the dependency is running and reachable from the service."
    )
    assert "asyncpg" not in message
    assert "ConnectionError" not in message


def test_retry_sync_retries_transient_failures_without_sleeping() -> None:
    from src.core.observability import RetryPolicy, retry_sync

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


def test_dependency_registry_tracks_required_and_degraded_states() -> None:
    from src.core.observability import DependencyPolicy, DependencyRegistry

    registry = DependencyRegistry()
    registry.record_ok("postgres", policy=DependencyPolicy.REQUIRED)
    registry.record_degraded("rag-service", hint="Knowledge tools degraded.")

    assert registry.ready() is True
    snapshot = registry.snapshot()
    assert snapshot["postgres"].status == "ok"
    assert snapshot["postgres"].ready is True
    assert snapshot["rag-service"].status == "degraded"
    assert snapshot["rag-service"].ready is True


def test_dependency_registry_not_ready_when_required_dependency_fails() -> None:
    from src.core.observability import DependencyPolicy, DependencyRegistry, DependencyStatus

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
