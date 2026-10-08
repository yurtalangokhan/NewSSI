"""Role distribution served as a background-refreshed snapshot.

Counting primary roles walks the whole Keycloak directory, which takes minutes on
a large realm. It is a dashboard statistic, so the request path only ever reads
the last computed value while one background task refreshes it.
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
import time
from typing import Any, Literal

from src.core.background_tasks import spawn_tracked
from src.core.observability import get_logger

logger = get_logger(__name__)

Status = Literal["ready", "pending", "unavailable"]
Distribution = list[dict[str, Any]]


class RoleDistributionSnapshot:
    """Stale-while-revalidate cache with a single in-flight refresh."""

    def __init__(
        self,
        compute: Callable[[], Awaitable[Distribution]],
        *,
        refresh_after: float = 300.0,
        retry_after: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._compute = compute
        self._refresh_after = refresh_after
        self._retry_after = retry_after
        self._clock = clock
        self._value: Distribution | None = None
        self._computed_at: datetime | None = None
        self._fresh_until = 0.0
        self._retry_at = 0.0
        self._failed = False
        self._task: asyncio.Task | None = None

    async def read(self) -> dict[str, Any]:
        now = self._clock()
        if self._should_refresh(now):
            self._task = spawn_tracked(self._refresh())
        return {
            "status": self._status(),
            "distribution": list(self._value or []),
            "computed_at": self._computed_at.isoformat() if self._computed_at else None,
        }

    def _running(self) -> bool:
        return self._task is not None and not self._task.done()

    def _should_refresh(self, now: float) -> bool:
        if self._running() or now < self._retry_at:
            return False
        return self._value is None or now >= self._fresh_until

    def _status(self) -> Status:
        if self._value is not None:
            return "ready"
        return "pending" if self._running() else "unavailable"

    async def _refresh(self) -> None:
        try:
            value = await self._compute()
        except Exception as exc:
            self._retry_at = self._clock() + self._retry_after
            logger.warning(
                "Role distribution refresh failed.",
                extra={
                    "event": "user.role_distribution.refresh_failed",
                    "error": type(exc).__name__,
                    "stale_value_served": self._value is not None,
                },
            )
            return
        self._value = value
        self._computed_at = datetime.now(UTC)
        self._fresh_until = self._clock() + self._refresh_after


_snapshot: RoleDistributionSnapshot | None = None


def get_role_distribution_snapshot() -> RoleDistributionSnapshot:
    global _snapshot
    if _snapshot is None:
        from src.repository import UserRepository

        async def compute() -> Distribution:
            return await UserRepository().count_by_role()

        _snapshot = RoleDistributionSnapshot(compute)
    return _snapshot
