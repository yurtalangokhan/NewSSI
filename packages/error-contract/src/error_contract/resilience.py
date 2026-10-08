"""Shared retry and circuit-breaker failures."""

from .exceptions import DependencyUnavailableError


class CircuitBreakerOpenError(DependencyUnavailableError):
    """An unavailable dependency whose circuit is temporarily open."""

    def __init__(self, name: str, reset_in_seconds: float):
        super().__init__(
            message=f"Circuit breaker '{name}' is OPEN. Reset in {reset_in_seconds:.1f}s",
            message_key="errors.dependency.unavailable",
        )
        self.name = name
        self.reset_in_seconds = reset_in_seconds
