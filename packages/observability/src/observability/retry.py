"""Bounded startup retries with the platform's structured retry logging.

Startup retries are a different availability concern from outbound HTTP
retries: a process coming up can wait longer per attempt than a request path
can, and each attempt must emit the operator fields (dependency, operation,
attempt, elapsed_ms) the readiness dashboards key on. The policy itself is not
hardcoded here: :meth:`RetryPolicy.for_dependency` resolves it from the shared
resilience policy (``configs/resilience.yaml``), so operators edit one file.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from .health import DependencyStartupError
from .sanitize import dependency_error_fields, is_retryable_exception, remediation_for_exception

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    """Configuration for bounded startup retries."""

    attempts: int = 5
    initial_delay_seconds: float = 0.5
    max_delay_seconds: float = 8.0
    multiplier: float = 2.0
    jitter: bool = True

    @classmethod
    def for_dependency(cls, dependency: str) -> RetryPolicy:
        """Resolve the startup retry policy for *dependency* from the shared policy.

        The shared resilience policy (``configs/resilience.yaml``) is the single
        place retry behaviour is declared; startup retries read the same file the
        outbound HTTP retries do. Jitter is always on for startup: many services
        coming up after a host restart must not retry in lockstep.
        """
        from security.resilience import retry_policy_for  # lazy: keeps `import observability` cheap

        settings = retry_policy_for(dependency)
        return cls(
            attempts=int(settings["max_attempts"]),
            initial_delay_seconds=float(settings["initial_backoff"]),
            multiplier=float(settings["multiplier"]),
            max_delay_seconds=float(settings["max_backoff"]),
            jitter=True,
        )


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    *,
    operation_name: str,
    dependency: str,
    policy: RetryPolicy | None = None,
    logger: logging.Logger | None = None,
) -> T:
    """Run an async startup operation with bounded retry."""

    retry_policy = policy or RetryPolicy.for_dependency(dependency)
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
            if not is_retryable_exception(exc):
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

    retry_policy = policy or RetryPolicy.for_dependency(dependency)
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
            if not is_retryable_exception(exc):
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
        policy.initial_delay_seconds * (policy.multiplier ** max(0, attempt - 1)),
        policy.max_delay_seconds,
    )
    if policy.jitter and delay > 0:
        return random.uniform(0, delay)
    return delay


def _dependency_startup_error(
    exc: BaseException,
    *,
    dependency: str,
    operation_name: str,
) -> DependencyStartupError:
    return DependencyStartupError(
        dependency=dependency,
        operation_name=operation_name,
        remediation=remediation_for_exception(exc),
    )
