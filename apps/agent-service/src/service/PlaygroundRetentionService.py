"""Playground Retention Service — cleans up expired playground threads.

Spec: .tmp/flow-canvas-design.md section 6.1 (retention TTL).
Brief: .tmp/flow-canvas-task-43-brief.md
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from core.db.repositories.thread_repo import ThreadRepository
from core.env import env
from core.logger import get_logger
from core.run_kinds import RunKind
from service.CheckpointerService import get_checkpointer

logger = get_logger(__name__)


class PlaygroundRetentionWorker:
    """Background worker that periodically sweeps and purges expired playground threads and checkpoints."""

    def __init__(self, repo: ThreadRepository | None = None) -> None:
        self._repo = repo or ThreadRepository()
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
            try:
                await self._task
            except asyncio.CancelledError:
                pass
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
        """Perform a single retention sweep pass.

        Returns:
            List of deleted thread_ids.
        """
        cutoff = datetime.now(UTC) - timedelta(days=env.PLAYGROUND_RETENTION_DAYS)
        deleted_ids = await self._repo.delete_threads_older_than(
            run_kind=RunKind.PLAYGROUND.value,
            older_than=cutoff,
        )
        if not deleted_ids:
            return []

        logger.info("Playground retention sweep removed %d expired thread(s)", len(deleted_ids))
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
