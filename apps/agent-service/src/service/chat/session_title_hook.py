"""Titles a session when its run completes, so naming no longer depends on the tab."""

from __future__ import annotations

from collections.abc import Callable

from service.chat.session_naming_service import SessionNamingService
from service.chat_runs.domain import ChatRun


class SessionTitleHook:
    def __init__(self, naming_factory: Callable[[], SessionNamingService]) -> None:
        self._naming_factory = naming_factory

    async def on_run_completed(self, run: ChatRun) -> None:
        await self._naming_factory().ensure_named(run.thread_id)
