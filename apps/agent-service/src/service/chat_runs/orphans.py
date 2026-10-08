"""Closing a run nobody is driving any more, without ever writing two run_end frames."""

from __future__ import annotations

from collections.abc import Awaitable

from core.observability.logger import get_logger
from service.chat_runs.domain import EventSequenceError, RunStatus
from service.chat_runs.frames import DONE_PAYLOAD, run_end_payload
from service.chat_runs.ports import Clock, RunEventLog, RunRegistry
from service.chat_runs.settings import ChatRunSettings

logger = get_logger(__name__)


async def _append_after_last(event_log: RunEventLog, run_id: str, payload: str, attempts: int) -> None:
    for _ in range(attempts):
        try:
            await event_log.append(run_id, await event_log.last_seq(run_id) + 1, payload)
            return
        except EventSequenceError:
            continue  # a fenced writer took the seq; re-read and try again
    raise EventSequenceError(run_id, -1)


async def _attempt(run_id: str, step: str, work: Awaitable[object]) -> None:
    try:
        await work
    except Exception:
        logger.warning("Could not %s of orphaned chat run %s", step, run_id, exc_info=True)


async def _release(registry: RunRegistry, run_id: str) -> None:
    run = await registry.get(run_id)
    if run is not None:
        await registry.release(run)


async def close_event_log(
    event_log: RunEventLog,
    run_id: str,
    status: RunStatus,
    error_code: str | None,
    *,
    max_attempts: int = 3,
) -> None:
    await _append_after_last(event_log, run_id, run_end_payload(status.value, error_code), max_attempts)
    await _append_after_last(event_log, run_id, DONE_PAYLOAD, max_attempts)


async def finalize_orphan(
    *,
    run_id: str,
    registry: RunRegistry,
    event_log: RunEventLog,
    settings: ChatRunSettings,
    clock: Clock,
    reason: str = "worker_lost",
) -> bool:
    if not await registry.mark_terminal(run_id, RunStatus.INTERRUPTED, error_code=reason, finished_at=clock.now()):
        return False
    try:
        await close_event_log(event_log, run_id, RunStatus.INTERRUPTED, reason)
    finally:
        # Bound the keys and free the thread even when the frames could not be
        # written. The steps are independent: a failed expire must not leave
        # the thread locked.
        await _attempt(run_id, "bound the event log", event_log.expire(run_id, settings.replay_ttl_seconds))
        await _attempt(run_id, "bound the run record", registry.expire(run_id, settings.replay_ttl_seconds))
        await _attempt(run_id, "release the thread", _release(registry, run_id))
    logger.warning(
        "Chat run finalized as orphan",
        extra={"event": "chat_run.orphan_finalized", "run_id": run_id, "reason": reason},
    )
    return True
