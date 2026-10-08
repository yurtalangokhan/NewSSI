"""Closes runs whose owning worker died (lease gone). Safe to run on every instance."""

from __future__ import annotations

import asyncio
import contextlib

from core.observability.logger import get_logger
from service.chat_runs.domain import RunStatus
from service.chat_runs.orphans import finalize_orphan
from service.chat_runs.ports import ChatRunMetrics, Clock, NoopChatRunMetrics, RunEventLog, RunRegistry, SystemClock
from service.chat_runs.settings import ChatRunSettings

logger = get_logger(__name__)


class OrphanRunReaper:
    def __init__(
        self,
        *,
        registry: RunRegistry,
        event_log: RunEventLog,
        settings: ChatRunSettings,
        clock: Clock | None = None,
        metrics: ChatRunMetrics | None = None,
    ) -> None:
        self._registry = registry
        self._log = event_log
        self._settings = settings
        self._clock = clock or SystemClock()
        self._task: asyncio.Task[None] | None = None
        self._metrics = metrics or NoopChatRunMetrics()

    async def reap_once(self) -> list[str]:
        reaped: list[str] = []
        for run_id in await self._registry.running_run_ids():
            if await self._registry.has_live_lease(run_id):
                continue
            try:
                if await finalize_orphan(
                    run_id=run_id,
                    registry=self._registry,
                    event_log=self._log,
                    settings=self._settings,
                    clock=self._clock,
                ):
                    reaped.append(run_id)
                    self._metrics.run_finished(RunStatus.INTERRUPTED, "worker_lost")
            except Exception:
                logger.exception("Could not reap chat run %s", run_id)
        return reaped

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="chat-run-reaper")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await self.reap_once()
            except Exception:
                logger.warning("Chat run reaper pass failed", exc_info=True)
            await asyncio.sleep(self._settings.reaper_interval_seconds)
