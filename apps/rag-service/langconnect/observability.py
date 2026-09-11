"""Observability helpers for rag-service."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

T = TypeVar("T")

_REDACTION_PATTERNS = (
    re.compile(r"://([^:/\s]+):([^@\s]+)@"),
    re.compile(r"(?i)\b(password|token|secret|api_key|apikey)=([^&\s]+)"),
)
_RESET = "\033[0m"
_LEVEL_COLORS = {
    "DEBUG": "\033[36m",
    "INFO": "\033[32m",
    "WARNING": "\033[33m",
    "ERROR": "\033[31m",
    "CRITICAL": "\033[35m",
}
_STATUS_COLORS = {
    "ok": "\033[32m",
    "ready": "\033[32m",
    "retrying": "\033[33m",
    "degraded": "\033[33m",
    "failed": "\033[31m",
    "not_ready": "\033[31m",
}


@dataclass(frozen=True)
class RetryPolicy:
    """Configuration for bounded startup retries."""

    attempts: int = 5
    initial_delay_seconds: float = 0.5
    max_delay_seconds: float = 8.0
    jitter: bool = True


class DependencyStartupError(RuntimeError):
    """Clean startup error for dependency failures."""

    def __init__(self, *, dependency: str, operation_name: str, remediation: str) -> None:
        """Build a safe dependency startup error."""
        super().__init__(
            f"{dependency} is unavailable during startup {operation_name}. {remediation}"
        )
        self.dependency = dependency
        self.operation_name = operation_name
        self.remediation = remediation


class DependencyPolicy(StrEnum):
    """Policy class for a startup dependency."""

    REQUIRED = "required"
    DEGRADED = "degraded"
    OPTIONAL = "optional"


@dataclass(frozen=True)
class DependencyStatus:
    """Immutable snapshot of one dependency's startup state."""

    name: str
    policy: DependencyPolicy
    status: str
    hint: str | None = None
    checked_at: str | None = None

    @property
    def ready(self) -> bool:
        """Whether this dependency allows the service to serve requests."""
        if self.status == "ok":
            return True
        if self.status == "degraded":
            return self.policy is not DependencyPolicy.REQUIRED
        return False


class DependencyRegistry:
    """In-memory registry of startup dependency states."""

    def __init__(self) -> None:
        """Initialise the dependency state store."""
        self._states: dict[str, DependencyStatus] = {}
        self._lock = threading.Lock()

    def record(self, status: DependencyStatus) -> None:
        """Store or replace the state for one dependency."""
        with self._lock:
            self._states[status.name] = status

    def record_ok(
        self, name: str, *, policy: DependencyPolicy = DependencyPolicy.REQUIRED
    ) -> None:
        """Record a healthy dependency state."""
        self.record(
            DependencyStatus(
                name=name,
                policy=policy,
                status="ok",
                checked_at=datetime.now(UTC).isoformat(),
            )
        )

    def record_degraded(self, name: str, *, hint: str | None = None) -> None:
        """Record a degraded dependency state."""
        self.record(
            DependencyStatus(
                name=name,
                policy=DependencyPolicy.DEGRADED,
                status="degraded",
                hint=hint,
                checked_at=datetime.now(UTC).isoformat(),
            )
        )

    def get(self, name: str) -> DependencyStatus | None:
        """Return the current state for one dependency."""
        with self._lock:
            return self._states.get(name)

    def snapshot(self) -> dict[str, DependencyStatus]:
        """Return a copy of all recorded dependency states."""
        with self._lock:
            return dict(self._states)

    def ready(self) -> bool:
        """True when no required dependency is unavailable."""
        with self._lock:
            return all(
                status.ready
                for status in self._states.values()
                if status.policy is DependencyPolicy.REQUIRED
            )


dependency_registry = DependencyRegistry()


def readiness_payload(*, service_name: str) -> dict[str, object]:
    """Build the readiness response payload from the dependency registry."""
    dependencies = {
        name: {
            "status": status.status,
            "required": status.policy is DependencyPolicy.REQUIRED,
            "hint": status.hint,
        }
        for name, status in dependency_registry.snapshot().items()
    }
    ready = dependency_registry.ready()
    return {
        "status": "ready" if ready else "not_ready",
        "service": service_name,
        "dependencies": dependencies,
    }


class JsonLogFormatter(logging.Formatter):
    """Format logs as compact JSON with the platform field contract."""

    def __init__(self, *, service_name: str) -> None:
        """Create the formatter for one service."""
        super().__init__()
        self._service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        """Return a JSON log line."""
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "service": getattr(record, "service", self._service_name),
            "logger": record.name,
            "event": getattr(record, "event", None),
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
            "dependency": getattr(record, "dependency", None),
            "operation": getattr(record, "operation", None),
            "attempt": getattr(record, "attempt", None),
            "max_attempts": getattr(record, "max_attempts", None),
            "elapsed_ms": getattr(record, "elapsed_ms", None),
            "status": getattr(record, "status", None),
        }
        if record.exc_info:
            payload.update(sanitize_exception(record.exc_info[1]))
        return json.dumps(payload, separators=(",", ":"))


class TextLogFormatter(logging.Formatter):
    """Format logs as compact text for local development."""

    def __init__(self, *, service_name: str) -> None:
        """Create the formatter for one service."""
        super().__init__()
        self._service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        """Return a text log line."""
        timestamp = datetime.fromtimestamp(record.created, UTC).isoformat()
        service = getattr(record, "service", self._service_name)
        event = getattr(record, "event", "app.log")
        level = _color(record.levelname, _LEVEL_COLORS.get(record.levelname))
        status = getattr(record, "status", None)
        fields = [
            f"service={service}",
            f"event={event}",
            *_optional_log_fields(record),
        ]
        if status:
            fields.append(f"status={_color(str(status), _STATUS_COLORS.get(str(status)))}")
        fields.append(f'message="{record.getMessage()}"')
        return f"{timestamp} {level} {' '.join(fields)}"


class LogFormat(StrEnum):
    """Supported log output formats."""

    TEXT = "text"
    JSON = "json"


def configure_logging(
    *,
    service_name: str = "rag-service",
    log_level: str = "INFO",
    log_format: str = "text",
) -> None:
    """Configure root logging once for rag-service."""
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    handler = logging.StreamHandler()
    selected_format = LogFormat(log_format.lower())
    if selected_format == LogFormat.JSON:
        handler.setFormatter(JsonLogFormatter(service_name=service_name))
    else:
        handler.setFormatter(TextLogFormatter(service_name=service_name))
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Return a logger that uses the configured root handlers."""
    return logging.getLogger(name)


def _color(value: str, color: str | None) -> str:
    """Apply ANSI color to text log values."""
    if not color:
        return value
    return f"{color}{value}{_RESET}"


def _optional_log_fields(record: logging.LogRecord) -> list[str]:
    """Return compact operator fields present on a log record."""
    fields: list[str] = []
    for key in ("dependency", "operation", "elapsed_ms", "error_code", "remediation"):
        value = getattr(record, key, None)
        if value is not None:
            fields.append(f"{key}={value}")

    attempt = getattr(record, "attempt", None)
    max_attempts = getattr(record, "max_attempts", None)
    if attempt is not None and max_attempts is not None:
        fields.append(f"attempt={attempt}/{max_attempts}")
    elif attempt is not None:
        fields.append(f"attempt={attempt}")
    return fields


def sanitize_exception(exc: BaseException | None) -> dict[str, str | bool | None]:
    """Return safe exception fields for logs and readiness details."""
    if exc is None:
        return {
            "exception_type": None,
            "exception_message": None,
            "retryable": False,
            "hint": None,
        }

    message = str(exc)
    for pattern in _REDACTION_PATTERNS:
        if pattern.pattern.startswith("://"):
            message = pattern.sub(r"://\1:[redacted]@", message)
        else:
            message = pattern.sub(lambda match: f"{match.group(1)}=[redacted]", message)

    return {
        "exception_type": exc.__class__.__name__,
        "exception_message": message,
        "retryable": _is_retryable_exception(exc),
        "hint": _hint_for_exception(exc),
    }


def dependency_error_fields(exc: BaseException, *, dependency: str) -> dict[str, str | bool]:
    """Return operator-facing dependency error fields without Python internals."""
    retryable = _is_retryable_exception(exc)
    return {
        "error_code": _error_code_for_exception(exc),
        "error_summary": f"{dependency} is unavailable.",
        "remediation": _remediation_for_exception(exc),
        "retryable": retryable,
    }


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    *,
    operation_name: str,
    dependency: str,
    policy: RetryPolicy | None = None,
    logger: logging.Logger | None = None,
) -> T:
    """Run an async startup operation with bounded retry."""
    retry_policy = policy or RetryPolicy()
    log = logger or logging.getLogger(__name__)
    last_exc: BaseException | None = None

    for attempt in range(1, retry_policy.attempts + 1):
        started = time.monotonic()
        try:
            result = await operation()
        except Exception as exc:
            last_exc = exc
            elapsed_ms = int((time.monotonic() - started) * 1000)
            if attempt >= retry_policy.attempts:
                raise _dependency_startup_error(
                    exc,
                    dependency=dependency,
                    operation_name=operation_name,
                ) from exc
            if not _is_retryable_exception(exc):
                raise
            log.warning(
                f"{dependency} is unavailable; retrying startup {operation_name}.",
                extra={
                    "event": "startup.dependency.retry",
                    "dependency": dependency,
                    "operation": operation_name,
                    "attempt": attempt,
                    "max_attempts": retry_policy.attempts,
                    "elapsed_ms": elapsed_ms,
                    "status": "retrying",
                    **dependency_error_fields(exc, dependency=dependency),
                },
            )
            await asyncio.sleep(_retry_delay(attempt, retry_policy))
        else:
            return result

    raise RuntimeError("Retry loop exited without result") from last_exc


def retry_sync(
    operation: Callable[[], T],
    *,
    operation_name: str,
    dependency: str,
    policy: RetryPolicy | None = None,
    logger: logging.Logger | None = None,
) -> T:
    """Run a sync startup operation with bounded retry."""
    retry_policy = policy or RetryPolicy()
    log = logger or logging.getLogger(__name__)
    last_exc: BaseException | None = None

    for attempt in range(1, retry_policy.attempts + 1):
        started = time.monotonic()
        try:
            return operation()
        except Exception as exc:
            last_exc = exc
            elapsed_ms = int((time.monotonic() - started) * 1000)
            if attempt >= retry_policy.attempts:
                raise _dependency_startup_error(
                    exc,
                    dependency=dependency,
                    operation_name=operation_name,
                ) from exc
            if not _is_retryable_exception(exc):
                raise
            log.warning(
                f"{dependency} is unavailable; retrying startup {operation_name}.",
                extra={
                    "event": "startup.dependency.retry",
                    "dependency": dependency,
                    "operation": operation_name,
                    "attempt": attempt,
                    "max_attempts": retry_policy.attempts,
                    "elapsed_ms": elapsed_ms,
                    "status": "retrying",
                    **dependency_error_fields(exc, dependency=dependency),
                },
            )
            time.sleep(_retry_delay(attempt, retry_policy))

    raise RuntimeError("Retry loop exited without result") from last_exc


def _retry_delay(attempt: int, policy: RetryPolicy) -> float:
    delay = min(
        policy.initial_delay_seconds * (2 ** max(0, attempt - 1)),
        policy.max_delay_seconds,
    )
    if policy.jitter and delay > 0:
        return random.uniform(0, delay)  # noqa: S311 - retry jitter is not secret material.
    return delay


def _is_retryable_exception(exc: BaseException) -> bool:
    return isinstance(exc, ConnectionError | TimeoutError | OSError)


def _hint_for_exception(exc: BaseException) -> str | None:
    if isinstance(exc, ConnectionError):
        return "Check that the dependency host and port are reachable."
    if isinstance(exc, TimeoutError):
        return "Check dependency readiness and network latency."
    return None


def _error_code_for_exception(exc: BaseException) -> str:
    if isinstance(exc, ConnectionError):
        return "dependency.connection_failed"
    if isinstance(exc, TimeoutError):
        return "dependency.timeout"
    return "dependency.unavailable"


def _remediation_for_exception(exc: BaseException) -> str:
    if isinstance(exc, TimeoutError):
        return "Check that the dependency is healthy and responds within the startup timeout."
    return "Check that the dependency is running and reachable from the service."


def _dependency_startup_error(
    exc: BaseException,
    *,
    dependency: str,
    operation_name: str,
) -> DependencyStartupError:
    return DependencyStartupError(
        dependency=dependency,
        operation_name=operation_name,
        remediation=_remediation_for_exception(exc),
    )
