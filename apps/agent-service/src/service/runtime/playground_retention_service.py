"""Playground Retention Service — cleans up expired playground threads.

Spec: .tmp/flow-canvas-design.md section 6.1 (retention TTL).
Brief: .tmp/flow-canvas-task-43-brief.md
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from config_manager import env

from core.observability.logger import get_logger
from core.types.run_kinds import RunKind
from infrastructure.runtime.checkpointer import get_checkpointer
from service.runtime import store_service

logger = get_logger(__name__)

#: Bulk-deletes threads of one run kind older than a cutoff, returning their ids.
DeleteExpiredThreads = Callable[[str, datetime], Awaitable[list[str]]]


class PlaygroundRetentionWorker:
    """Background worker that periodically sweeps and purges expired playground threads and checkpoints."""

    def __init__(
        self,
        delete_expired: DeleteExpiredThreads | None = None,
        delete_inactive: DeleteExpiredThreads | None = None,
    ) -> None:
        # Thread persistence goes through StoreService — the single access path
        # for the thread table in the service layer. Injected only for tests.
        self._delete_expired = delete_expired or store_service.delete_threads_older_than
        self._delete_inactive = delete_inactive or store_service.delete_threads_inactive_since
        self._task: asyncio.Task | None = None
        self._running = False

    def start(self) -> None:
        """Start the background sweep task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(
            self._poll_loop(),
            name="playground-retention",
        )
        logger.info(
            "PlaygroundRetentionWorker started (TTL=%d days, poll every %ds)",
            env.PLAYGROUND_RETENTION_DAYS,
            env.PLAYGROUND_RETENTION_POLL_INTERVAL_SECONDS,
        )

    async def stop(self) -> None:
        """Gracefully stop the worker."""
        self._running = False
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        logger.info("PlaygroundRetentionWorker stopped")

    async def _poll_loop(self) -> None:
        """Long-running coroutine that periodically sweeps expired playground runs."""
        # Initial delay to let services warm up
        await asyncio.sleep(env.PLAYGROUND_RETENTION_STARTUP_DELAY_SECONDS)

        while self._running:
            try:
                await self.sweep_once()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Playground retention sweep failed")

            try:
                await asyncio.sleep(env.PLAYGROUND_RETENTION_POLL_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                break

    async def sweep_once(self) -> list[str]:
        """Perform a single retention sweep pass across every configured run kind.

        Playground runs are always swept (creation-time TTL -- they're
        short-lived by design). Production (real conversation) threads are
        only swept when PRODUCTION_RETENTION_DAYS is configured above 0,
        using inactivity rather than creation time as the cutoff, since a
        long-lived thread a user still chats in must not be deleted just
        for being old.

        Returns:
            Combined list of deleted thread_ids across every run kind swept.
        """
        deleted_ids: list[str] = []

        playground_cutoff = datetime.now(UTC) - timedelta(days=env.PLAYGROUND_RETENTION_DAYS)
        playground_deleted = await self._delete_expired(
            RunKind.PLAYGROUND.value,
            playground_cutoff,
        )
        if playground_deleted:
            logger.info("Playground retention sweep removed %d expired thread(s)", len(playground_deleted))
        deleted_ids.extend(playground_deleted)

        if env.PRODUCTION_RETENTION_DAYS > 0:
            production_cutoff = datetime.now(UTC) - timedelta(days=env.PRODUCTION_RETENTION_DAYS)
            production_deleted = await self._delete_inactive(
                RunKind.PRODUCTION.value,
                production_cutoff,
            )
            if production_deleted:
                logger.info(
                    "Production retention sweep removed %d inactive thread(s)",
                    len(production_deleted),
                )
            deleted_ids.extend(production_deleted)

        if not deleted_ids:
            return []

        saver = get_checkpointer()
        for tid in deleted_ids:
            if saver and hasattr(saver, "adelete_thread"):
                try:
                    await saver.adelete_thread(tid)
                except Exception as exc:
                    logger.warning("Could not purge checkpointer state for thread %s: %s", tid, exc)

        return deleted_ids


_worker: PlaygroundRetentionWorker | None = None


def get_playground_retention_worker() -> PlaygroundRetentionWorker:
    """Singleton getter for PlaygroundRetentionWorker."""
    global _worker
    if _worker is None:
        _worker = PlaygroundRetentionWorker()
    return _worker
