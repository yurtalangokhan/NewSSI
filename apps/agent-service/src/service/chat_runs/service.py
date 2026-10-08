"""Use-case facade for chat runs; the only chat-run entry point routes use."""

from __future__ import annotations

from collections.abc import AsyncIterator, Collection

from core.observability.logger import get_logger
from service.chat_runs.domain import (
    ChatRun,
    ChatRunSpec,
    ChatRunUnavailableError,
    RunAlreadyActiveError,
    RunNotFoundError,
)
from service.chat_runs.ports import RunRegistry
from service.chat_runs.reader import RunEventReader
from service.chat_runs.supervisor import ChatRunSupervisor, FrameSource

logger = get_logger(__name__)


class ChatRunService:
    def __init__(self, *, supervisor: ChatRunSupervisor, reader: RunEventReader, registry: RunRegistry) -> None:
        self._supervisor = supervisor
        self._reader = reader
        self._registry = registry

    async def start(self, spec: ChatRunSpec, frames: FrameSource) -> ChatRun:
        return await self._supervisor.start(spec, frames)

    async def ensure_idle(self, thread_id: str, *, owner_ids: Collection[str]) -> None:
        """Reject a send to a busy chat before the caller mutates anything.

        This is an early, cheap rejection so a busy chat has no side effects.
        ``start`` stays the atomic gate when two sends race past this check.
        """
        try:
            busy = await self.get_active_run(thread_id, owner_ids=owner_ids)
        except Exception as exc:
            logger.exception("Could not check the active run for thread %s", thread_id)
            raise ChatRunUnavailableError("active-run lookup failed") from exc
        if busy is not None:
            raise RunAlreadyActiveError(busy.run_id)

    async def start_and_subscribe(self, spec: ChatRunSpec, frames: FrameSource) -> tuple[ChatRun, AsyncIterator[str]]:
        """Start a run and subscribe its owner to the event stream.

        The run lives in the supervisor, so the returned stream is only a
        subscriber: closing it never touches the run.
        """
        try:
            run = await self._supervisor.start(spec, frames)
        except ChatRunUnavailableError:
            logger.exception("Chat run could not be started for thread %s", spec.thread_id)
            raise
        events = await self.open_events(run.run_id, after_seq=0, owner_ids={run.owner_user_id})
        return run, events

    async def get_active_run(self, thread_id: str, *, owner_ids: Collection[str]) -> ChatRun | None:
        run = await self._registry.get_active_for_thread(thread_id)
        return run if run is not None and run.owner_user_id in owner_ids else None

    async def active_thread_ids(self, thread_ids: Collection[str], *, owner_ids: Collection[str]) -> set[str]:
        """Threads among *thread_ids* holding a live run owned by the caller.

        Batched counterpart of :meth:`get_active_run` for list endpoints: one
        registry round trip instead of one per thread.
        """
        runs = await self._registry.active_runs_for_threads(list(thread_ids))
        return {thread_id for thread_id, run in runs.items() if run.owner_user_id in owner_ids}

    async def open_events(self, run_id: str, *, after_seq: int, owner_ids: Collection[str]) -> AsyncIterator[str]:
        run = await self._registry.get(run_id)
        if run is None or run.owner_user_id not in owner_ids:
            raise RunNotFoundError(run_id)  # never reveal that someone else's run exists
        return self._reader.stream(run_id, after_seq)

    async def cancel_active(self, thread_id: str, *, client_request_id: str | None = None) -> bool:
        """Stop the thread's run, including a send that is not registered yet.

        A run on this instance is stopped first and needs no registry. The
        registry then records the Stop for a run on another instance, or for a
        send that is not registered yet. If it is down, a local stop still
        succeeds; otherwise the Stop cannot be recorded and is reported as
        unavailable.
        """
        stopped_here = self._supervisor.cancel_local_for_thread(thread_id)
        try:
            return await self._cancel_registered(thread_id, client_request_id) or stopped_here
        except Exception as exc:
            if stopped_here:
                logger.warning(
                    "Stop reached the local run but the registry is down for thread %s", thread_id, exc_info=True
                )
                return True
            raise ChatRunUnavailableError("stop could not be recorded") from exc

    async def _cancel_registered(self, thread_id: str, client_request_id: str | None) -> bool:
        """The request mark is written before the lookup and the supervisor checks
        it after acquiring the thread, so whichever order the two land in,
        one of them sees the other: a Stop is never lost to the gap between
        the send being accepted and its run being registered.
        """
        if client_request_id:
            await self._registry.request_cancel_for_request(
                thread_id, client_request_id, ttl_seconds=self._supervisor.request_cancel_ttl_seconds
            )
        run = await self._registry.get_active_for_thread(thread_id)
        if run is None:
            return False
        return await self._supervisor.cancel(run.run_id)
