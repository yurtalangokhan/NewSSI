"""Advances a thread's message activity when its run finishes producing an answer.

The sidebar's unread dot compares the newest message against the last time the
chat was opened, and the accepted user send alone goes stale the moment the user
reloads the open chat. Recording the completed answer here — on whichever
instance owns the run — keeps that comparison meaningful even when no browser is
attached.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from core.observability.logger import get_logger
from service.chat_runs.domain import ChatRun, RunStatus
from service.threads import get_thread_access_service

logger = get_logger(__name__)


class AnswerActivityHook:
    def __init__(self, thread_service_factory: Callable[[], Any] | None = None) -> None:
        self._thread_service_factory = thread_service_factory or get_thread_access_service

    async def on_run_completed(self, run: ChatRun) -> None:
        # The supervisor only dispatches this for COMPLETED runs, but a hook must
        # not depend on that: a cancelled or interrupted run has no new answer.
        if run.status is not RunStatus.COMPLETED:
            return
        # Stamp the instant the run finished, not "now": the client only learns
        # the answer is done after that, so its later /seen stays newer than the
        # answer whichever of the two requests reaches the database first.
        finished = datetime.fromtimestamp(run.finished_at, UTC) if run.finished_at is not None else None
        try:
            await self._thread_service_factory().mark_answer_activity(run.thread_id, at=finished)
        except Exception:
            logger.warning(
                "Could not record answer activity for thread %s",
                run.thread_id,
                exc_info=True,
            )
