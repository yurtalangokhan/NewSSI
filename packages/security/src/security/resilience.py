"""Strictly bounded retry, circuit breaking, and policy loading.

Mechanism only. A service supplies its own policy file location and timeout
tables; nothing here knows which service is calling.
"""

import asyncio
import logging
import os
import threading
import time
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import Any, TypeVar

import httpx
import yaml
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    wait_exponential_jitter,
)


class CircuitState(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

class CircuitBreakerOpenError(Exception):
    """Raised when an operation is attempted on an OPEN circuit breaker."""
    def __init__(self, name: str, reset_in_seconds: float):
        super().__init__(f"Circuit breaker '{name}' is OPEN. Reset in {reset_in_seconds:.1f}s")
        self.name = name
        self.reset_in_seconds = reset_in_seconds

class CircuitBreaker:
    """
    Thread-safe asynchronous circuit breaker implementation.
    """
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        reset_timeout_seconds: float = 30.0,
        half_open_max_calls: int = 2,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_timeout_seconds = reset_timeout_seconds
        self.half_open_max_calls = half_open_max_calls

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_state_change = time.monotonic()
        #: Trial calls admitted during the current HALF_OPEN window that
        #: have not yet reported success or failure.
        self.half_open_calls = 0
        self._lock = asyncio.Lock()

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            await self.record_failure()
        else:
            await self.record_success()
        return False

    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            if self.state == CircuitState.OPEN:
                elapsed = now - self.last_state_change
                if elapsed >= self.reset_timeout_seconds:
                    self.state = CircuitState.HALF_OPEN
                    self.last_state_change = now
                    self.half_open_calls = 0
                else:
                    raise CircuitBreakerOpenError(
                        self.name, self.reset_timeout_seconds - elapsed
                    )

            if self.state == CircuitState.HALF_OPEN:
                if self.half_open_calls >= self.half_open_max_calls:
                    raise CircuitBreakerOpenError(self.name, self.reset_timeout_seconds)
                self.half_open_calls += 1

    async def record_success(self):
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                # Every admitted trial call must succeed before the circuit
                # closes -- closing on the first success while siblings are
                # still in flight would let a single lucky trial mask a
                # concurrent one that goes on to fail (see record_failure).
                self.half_open_calls = max(0, self.half_open_calls - 1)
                if self.half_open_calls == 0:
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.last_state_change = time.monotonic()
            elif self.state == CircuitState.CLOSED:
                self.failure_count = 0

    async def record_failure(self):
        async with self._lock:
            self.failure_count += 1
            if self.state == CircuitState.HALF_OPEN or self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                self.last_state_change = time.monotonic()
                self.half_open_calls = 0


#: Retained so existing imports keep working; ``CircuitBreakerOpenError`` is the
#: name to use.
CircuitBreakerOpenException = CircuitBreakerOpenError

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerOpenError",
    "CircuitBreakerOpenException",
    "CircuitState",
]


logger = logging.getLogger(__name__)

T = TypeVar("T")

#: Failures worth retrying: the request never reached a handler, or the peer
#: gave up before answering. A response the server actually produced — including
#: a 5xx — is not retried here; that is the circuit breaker's job.
TRANSIENT_HTTP_EXCEPTIONS: tuple[type[BaseException], ...] = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.RemoteProtocolError,
)

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_INITIAL_BACKOFF = 0.2
DEFAULT_MULTIPLIER = 2.0
DEFAULT_MAX_BACKOFF = 2.0


def _wait_strategy(
    *,
    initial_backoff: float,
    multiplier: float,
    max_backoff: float,
    jitter: float,
):
    """Build the tenacity wait matching the declared backoff curve.

    ``wait_exponential`` computes ``multiplier * exp_base ** (attempt_number - 1)``.
    Its ``multiplier`` is therefore the *first* wait, and the policy's growth
    factor belongs in ``exp_base``. Putting the policy multiplier into
    ``multiplier`` — the obvious-looking mapping, and the one that shipped —
    yields 2s, 4s, 8s against a 2s ceiling, so every retry waits the maximum and
    the configured ``initialSeconds`` never applies.
    """
    if multiplier <= 0:
        multiplier = DEFAULT_MULTIPLIER
    if jitter > 0:
        return wait_exponential_jitter(
            initial=initial_backoff,
            exp_base=multiplier,
            max=max_backoff,
            jitter=jitter,
        )
    return wait_exponential(
        multiplier=initial_backoff,
        exp_base=multiplier,
        max=max_backoff,
    )


def retry_waits(
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    initial_backoff: float = DEFAULT_INITIAL_BACKOFF,
    multiplier: float = DEFAULT_MULTIPLIER,
    max_backoff: float = DEFAULT_MAX_BACKOFF,
) -> list[float]:
    """Return the un-jittered wait before each retry, for inspection and tests."""
    wait = _wait_strategy(
        initial_backoff=initial_backoff,
        multiplier=multiplier,
        max_backoff=max_backoff,
        jitter=0.0,
    )

    class _State:
        def __init__(self, attempt_number: int) -> None:
            self.attempt_number = attempt_number

    return [wait(_State(attempt)) for attempt in range(1, max_attempts)]


def bounded_retry(
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    initial_backoff: float = DEFAULT_INITIAL_BACKOFF,
    max_backoff: float = DEFAULT_MAX_BACKOFF,
    multiplier: float = DEFAULT_MULTIPLIER,
    jitter: float = 0.1,
    retry_exceptions: tuple[type[BaseException], ...] = TRANSIENT_HTTP_EXCEPTIONS,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorate a call with a hard attempt ceiling and exponential backoff.

    ``max_attempts`` counts the first call, so ``3`` means one call and two
    retries. Jitter spreads retries from many callers that failed at the same
    instant; set it to ``0`` for deterministic timing in tests.
    """
    wait = _wait_strategy(
        initial_backoff=initial_backoff,
        multiplier=multiplier,
        max_backoff=max_backoff,
        jitter=jitter if max_backoff > 0 else 0.0,
    )

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        return retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait,
            retry=retry_if_exception_type(retry_exceptions),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )(fn)

    return decorator


__all__: list[Any] = [
    "DEFAULT_INITIAL_BACKOFF",
    "DEFAULT_MAX_ATTEMPTS",
    "DEFAULT_MAX_BACKOFF",
    "DEFAULT_MULTIPLIER",
    "TRANSIENT_HTTP_EXCEPTIONS",
    "bounded_retry",
    "retry_waits",
]


#: config still gets bounded behaviour rather than unbounded retries.
#: The postgres/redis sections mirror configs/resilience.yaml: startup
#: dependency retries (packages/observability) resolve through the same
#: policy, and containers that do not carry configs/ must keep the same
#: patient startup values rather than inheriting the request-path defaults.
_FALLBACK_POLICY: dict[str, Any] = {
    "defaults": {
        "timeoutSeconds": 15,
        "retry": {
            "maxAttempts": DEFAULT_MAX_ATTEMPTS,
            "backoff": {
                "initialSeconds": DEFAULT_INITIAL_BACKOFF,
                "multiplier": DEFAULT_MULTIPLIER,
                "maxSeconds": DEFAULT_MAX_BACKOFF,
            },
        },
        "circuitBreaker": {"failureThreshold": 5, "resetTimeoutSeconds": 30},
    },
    "dependencies": {
        "postgres": {
            "retry": {
                "maxAttempts": 5,
                "backoff": {"initialSeconds": 0.5, "multiplier": 2.0, "maxSeconds": 8.0},
            },
        },
        "redis": {
            "retry": {
                "maxAttempts": 5,
                "backoff": {"initialSeconds": 0.5, "multiplier": 2.0, "maxSeconds": 8.0},
            },
        },
    },
}

_lock = threading.Lock()
_policy_config: dict[str, Any] | None = None
_circuit_breakers: dict[str, CircuitBreaker] = {}


def _discover_policy_path() -> str | None:
    """Locate ``configs/resilience.yaml`` without depending on the process CWD.

    ``RESILIENCE_CONFIG_PATH`` wins. Otherwise the repository layout is walked
    upward from this file, which works from a checkout and from a container that
    copied ``configs/`` alongside the service.
    """
    override = os.environ.get("RESILIENCE_CONFIG_PATH")
    if override and Path(override).is_file():
        return override

    for parent in Path(__file__).resolve().parents:
        candidate = parent / "configs" / "resilience.yaml"
        if candidate.is_file():
            return str(candidate)

    cwd_candidate = Path.cwd() / "configs" / "resilience.yaml"
    return str(cwd_candidate) if cwd_candidate.is_file() else None


def load_resilience_config(config_path: str | None = None) -> dict[str, Any]:
    """Load and cache the policy. Passing a path reloads from that file."""
    global _policy_config
    with _lock:
        if config_path is None and _policy_config is not None:
            return _policy_config

        path = config_path or _discover_policy_path()
        if path and Path(path).is_file():
            loaded = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        else:
            loaded = _FALLBACK_POLICY

        _policy_config = loaded
        if config_path is not None:
            _circuit_breakers.clear()
        return _policy_config


def reset_policy_cache() -> None:
    """Drop the cached policy and every breaker built from it."""
    global _policy_config
    with _lock:
        _policy_config = None
        _circuit_breakers.clear()


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge *override* onto *base*, recursing into nested dicts on both sides.

    A shallow ``{**base, **override}`` replaces a nested dict wholesale the
    moment *override* supplies even one of its keys -- a dependency meaning to
    override just ``retry.backoff.maxSeconds`` would silently lose the policy
    file's own ``initialSeconds``/``multiplier`` defaults, falling back to this
    module's hardcoded constants instead. Recursing keeps sibling keys the
    override never mentioned.
    """
    merged = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = _deep_merge(merged[k], v)
        else:
            merged[k] = v
    return merged


def _section(dependency: str, key: str) -> dict[str, Any]:
    config = load_resilience_config()
    defaults = (config.get("defaults") or {}).get(key) or {}
    override = ((config.get("dependencies") or {}).get(dependency) or {}).get(key) or {}
    return _deep_merge(defaults, override)


def timeout_for(dependency: str) -> float:
    """Per-request timeout in seconds for *dependency*."""
    config = load_resilience_config()
    defaults = config.get("defaults") or {}
    override = (config.get("dependencies") or {}).get(dependency) or {}
    return float(override.get("timeoutSeconds", defaults.get("timeoutSeconds", 15)))


def retry_policy_for(dependency: str) -> dict[str, Any]:
    """Resolved retry settings for *dependency*, as :func:`bounded_retry` kwargs."""
    retry_cfg = _section(dependency, "retry")
    backoff = retry_cfg.get("backoff") or {}
    return {
        "max_attempts": int(retry_cfg.get("maxAttempts", DEFAULT_MAX_ATTEMPTS)),
        "initial_backoff": float(backoff.get("initialSeconds", DEFAULT_INITIAL_BACKOFF)),
        "multiplier": float(backoff.get("multiplier", DEFAULT_MULTIPLIER)),
        "max_backoff": float(backoff.get("maxSeconds", DEFAULT_MAX_BACKOFF)),
    }


def retry_for(dependency: str):
    """Return a :func:`bounded_retry` decorator configured for *dependency*."""
    return bounded_retry(**retry_policy_for(dependency))


def get_circuit_breaker(name: str) -> CircuitBreaker:
    """Return the process-wide breaker for *name*, building it from the policy."""
    breaker_cfg = _section(name, "circuitBreaker")
    with _lock:
        breaker = _circuit_breakers.get(name)
        if breaker is None:
            breaker = CircuitBreaker(
                name=name,
                failure_threshold=int(breaker_cfg.get("failureThreshold", 5)),
                reset_timeout_seconds=float(breaker_cfg.get("resetTimeoutSeconds", 30.0)),
            )
            _circuit_breakers[name] = breaker
        return breaker


__all__ = [
    "get_circuit_breaker",
    "load_resilience_config",
    "reset_policy_cache",
    "retry_for",
    "retry_policy_for",
    "timeout_for",
]
