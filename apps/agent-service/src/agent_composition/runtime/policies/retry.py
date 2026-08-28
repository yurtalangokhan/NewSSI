"""Retry and timeout policy using the RuntimePolicy protocol.

The RetryPolicy wraps runtime operations (invoke, stream, state access)
with configurable retry, timeout, and telemetry. It does not implement
business fallback responses.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any, TypeVar

from agent_composition.domain.ports import (
    RuntimePolicyDecision,
    RuntimePolicyRequest,
    RuntimePolicyResult,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")
RetryOperation = Coroutine[Any, Any, T] | Callable[[], Coroutine[Any, Any, T]]


@dataclass(frozen=True)
class RetryPolicyConfig:
    """Configuration for the retry policy."""

    enabled: bool = False
    max_attempts: int = 2
    initial_delay: float = 0.5
    max_delay: float = 5.0
    exponential_base: float = 2.0
    # Timeout per operation in seconds (0 = no timeout).
    timeout_seconds: float = 0


class RetryPolicy:
    """Retry, timeout, and telemetry around declared runtime operations.

    This policy implements the RuntimePolicy protocol. It wraps agent
    invoke/stream/state operations with retry logic and timeout enforcement.
    """

    key: str = "retry"

    def __init__(self, config: RetryPolicyConfig | None = None) -> None:
        self._config = config or RetryPolicyConfig()

    @property
    def is_enabled(self) -> bool:
        return self._config.enabled

    async def before_run(self, request: RuntimePolicyRequest) -> RuntimePolicyDecision:
        """Check before a run — currently always allows."""
        if not self._config.enabled:
            return RuntimePolicyDecision(continue_run=True, reason="retry disabled")
        return RuntimePolicyDecision(continue_run=True, reason="retry enabled")

    async def after_run(self, request: RuntimePolicyRequest, result: Any) -> RuntimePolicyResult:
        """Check after a run — currently always passes."""
        if not self._config.enabled:
            return RuntimePolicyResult(metadata={"skipped": "retry disabled"})
        return RuntimePolicyResult(metadata={"attempts": 1})

    async def close(self) -> None:
        """Retry policy has no persistent resources to close."""
        pass

    async def run_with_retry(
        self,
        operation: RetryOperation[T],
        operation_name: str = "operation",
    ) -> T:
        """Execute a coroutine with retry and timeout.

        This is the primary method for wrapping invoke/stream calls with
        the configured retry policy.
        """
        if not self._config.enabled:
            return await self._new_operation(operation)

        delay = self._config.initial_delay
        last_exc: Exception | None = None

        for attempt in range(1, self._config.max_attempts + 1):
            try:
                coro = self._new_operation(operation)
                if self._config.timeout_seconds > 0:
                    return await asyncio.wait_for(coro, timeout=self._config.timeout_seconds)
                return await coro
            except TimeoutError as exc:
                last_exc = exc
                logger.warning(
                    "[RetryPolicy] %s timed out after %.1fs (attempt %d/%d)",
                    operation_name,
                    self._config.timeout_seconds,
                    attempt,
                    self._config.max_attempts,
                )
            except Exception as exc:  # pragma: no cover
                last_exc = exc
                logger.warning(
                    "[RetryPolicy] %s failed: %s (attempt %d/%d)",
                    operation_name,
                    exc,
                    attempt,
                    self._config.max_attempts,
                )

            if attempt < self._config.max_attempts:
                await asyncio.sleep(delay)
                delay = min(delay * self._config.exponential_base, self._config.max_delay)

        # All attempts exhausted
        if last_exc is not None:
            raise last_exc  # pragma: no cover
        raise RuntimeError(
            f"[RetryPolicy] {operation_name} failed after {self._config.max_attempts} attempts"
        )

    def _new_operation(self, operation: RetryOperation[T]) -> Coroutine[Any, Any, T]:
        if callable(operation):
            return operation()
        return operation
