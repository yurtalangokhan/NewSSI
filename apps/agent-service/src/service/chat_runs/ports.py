"""Ports the chat-run services depend on. Adapters live in infrastructure/."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
import time
from typing import Protocol

from service.chat_runs.domain import ChatRun, RunEvent, RunStatus


class Clock(Protocol):
    def now(self) -> float: ...


class SystemClock:
    def now(self) -> float:
        return time.time()


class RunEventLog(Protocol):
    async def append(self, run_id: str, seq: int, payload: str) -> None: ...

    async def read_after(
        self, run_id: str, after_seq: int, *, block_seconds: float = 0.0, limit: int = 500
    ) -> list[RunEvent]: ...

    async def last_seq(self, run_id: str) -> int: ...

    async def expire(self, run_id: str, ttl_seconds: int) -> None: ...


@dataclass(frozen=True, slots=True)
class AcquireResult:
    acquired: bool
    holder_run_id: str | None = None
    reclaimed_run_id: str | None = None


class RunRegistry(Protocol):
    async def try_acquire(
        self, run: ChatRun, *, lease_ttl_seconds: float, run_ttl_seconds: float | None = None
    ) -> AcquireResult:
        """``run_ttl_seconds`` bounds the run record's lifetime from the moment it exists."""
        ...

    async def get(self, run_id: str) -> ChatRun | None: ...

    async def get_active_for_thread(self, thread_id: str) -> ChatRun | None: ...

    async def active_runs_for_threads(self, thread_ids: Collection[str]) -> dict[str, ChatRun]:
        """Batched ``get_active_for_thread``: live, running runs keyed by thread id.

        Listing a page of chats must not fan out into one lookup per row, so
        adapters answer this in a bounded number of round trips.
        """
        ...

    async def renew_lease(self, run_id: str, instance_id: str, *, lease_ttl_seconds: float) -> bool: ...

    async def has_live_lease(self, run_id: str) -> bool: ...

    async def mark_terminal(
        self, run_id: str, status: RunStatus, *, error_code: str | None, finished_at: float
    ) -> bool: ...

    async def release(self, run: ChatRun) -> None: ...

    async def request_cancel(self, run_id: str, *, ttl_seconds: int) -> None: ...

    async def is_cancel_requested(self, run_id: str) -> bool: ...

    async def request_cancel_for_request(self, thread_id: str, client_request_id: str, *, ttl_seconds: int) -> None:
        """Mark a Stop for a send that may not be registered as a run yet."""
        ...

    async def is_request_cancelled(self, thread_id: str, client_request_id: str) -> bool: ...

    async def running_run_ids(self) -> list[str]: ...

    async def expire(self, run_id: str, ttl_seconds: int) -> None: ...


# End reasons the platform itself produces. Anything else is an agent or
# provider error code: collapsed so metric label sets stay bounded.
_KNOWN_REASONS = frozenset(
    {
        "cancelled",
        "shutdown",
        "lease_lost",
        "worker_lost",
        "run_timeout",
        "internal_error",
        "event_log_unavailable",
        "run_expired",
    }
)


def bounded_reason(error_code: str | None) -> str:
    if error_code is None:
        return "none"
    return error_code if error_code in _KNOWN_REASONS else "agent_error"


class ChatRunMetrics(Protocol):
    """Health signals of the chat-run runtime (see the Prometheus adapter)."""

    def run_started(self) -> None: ...

    def run_ended(self) -> None: ...

    def run_finished(self, status: RunStatus, reason: str) -> None:
        """A terminal status this process recorded (first writer wins)."""
        ...

    def heartbeat_lag(self, seconds: float) -> None:
        """How late a lease heartbeat woke up: event-loop stall time."""
        ...

    def stream_opened(self) -> None: ...

    def stream_closed(self) -> None: ...


class NoopChatRunMetrics:
    def run_started(self) -> None:
        pass

    def run_ended(self) -> None:
        pass

    def run_finished(self, status: RunStatus, reason: str) -> None:
        pass

    def heartbeat_lag(self, seconds: float) -> None:
        pass

    def stream_opened(self) -> None:
        pass

    def stream_closed(self) -> None:
        pass
