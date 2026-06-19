"""Run controller - handles SDK-compatible run execution and streaming."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from langchain_core.runnables import RunnableConfig

from controller.base import BaseController
from service.RunService import RunService


class RunController(BaseController):
    """Controller for SDK-compatible run execution and streaming."""

    def __init__(self):
        self._service = RunService()

    async def event_generator(
        self,
        agent: Any,
        input_messages: list[Any],
        config: RunnableConfig,
        thread_id: str,
        run_id: str,
        stream_mode: list[str],
        user_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        if not thread_id or not run_id:
            self._raise_bad_request("thread_id and run_id are required")
        try:
            return self._service.event_generator(
                agent, input_messages, config, thread_id, run_id, stream_mode, user_id
            )
        except Exception as exc:
            self._raise_internal_error(str(exc))

    async def cancel_run(self, thread_id: str, run_id: str) -> dict[str, Any]:
        if not thread_id or not run_id:
            self._raise_bad_request("thread_id and run_id are required")
        try:
            return await self._service.cancel_run(thread_id, run_id)
        except Exception as exc:
            self._raise_internal_error(str(exc))

    async def get_thread_history(
        self, thread_id: str, limit: int = 100, before: str | None = None
    ) -> list[dict[str, Any]]:
        if not thread_id:
            self._raise_bad_request("thread_id is required")
        try:
            return await self._service.get_thread_history(thread_id, limit, before)
        except Exception as exc:
            self._raise_internal_error(str(exc))


# Singleton instance
_run_controller: RunController | None = None


def get_run_controller() -> RunController:
    """Get the singleton RunController instance."""
    global _run_controller
    if _run_controller is None:
        _run_controller = RunController()
    return _run_controller
