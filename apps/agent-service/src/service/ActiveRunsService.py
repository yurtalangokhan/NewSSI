"""
Active run registry — tracks in-flight runs so they can be cancelled.

Each run is identified by ``(thread_id, run_id)`` and is associated with an
``asyncio.Event`` that the streaming generator checks periodically.  When
``cancel()`` is called the event is set and the generator breaks out of its
loop.

A companion ``_run_contexts`` dict keeps references to the agent, config,
accumulated messages and checkpointer so that the generator's ``finally``
block (which runs even when the HTTP connection is aborted) can persist
partial messages into the checkpoint.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any

from core.logger import get_logger

logger = get_logger(__name__)

# (thread_id, run_id) → asyncio.Event (set = cancelled)
_active_runs: dict[tuple[str, str], asyncio.Event] = {}


@dataclass
class RunContext:
    """Mutable bag of state shared between the streaming generator and the
    finally-block / cancel endpoint so partial messages can be persisted."""

    agent: Any = None
    config: dict | None = None
    all_messages: list[dict] = field(default_factory=list)
    checkpointer: Any = None
    agent_task: asyncio.Task | None = None


_run_contexts: dict[tuple[str, str], RunContext] = {}


def register_run(thread_id: str, run_id: str) -> asyncio.Event:
    """Register a new run and return its cancellation event."""
    cancel_event = asyncio.Event()
    _active_runs[(thread_id, run_id)] = cancel_event
    _run_contexts[(thread_id, run_id)] = RunContext()
    logger.debug("Registered run %s on thread %s", run_id, thread_id)
    return cancel_event


def get_run_context(thread_id: str, run_id: str) -> RunContext | None:
    """Return the RunContext for an active run, or None."""
    return _run_contexts.get((thread_id, run_id))


def cancel_run(thread_id: str, run_id: str) -> bool:
    """
    Signal a run to stop.

    Returns ``True`` if the run was found and signalled, ``False`` if the
    run is not (or no longer) active.
    """
    cancel_event = _active_runs.get((thread_id, run_id))
    if cancel_event is None:
        logger.debug("Run %s on thread %s not found (already finished?)", run_id, thread_id)
        return False
    cancel_event.set()
    ctx = _run_contexts.get((thread_id, run_id))
    if ctx and ctx.config:
        try:
            import asyncio as _aio

            from routes.RunRoute import _force_close_llm_connection

            _aio.ensure_future(_force_close_llm_connection(ctx.config))
            logger.info("Scheduled _force_close_llm_connection for run %s", run_id)
        except Exception as exc:
            logger.warning("cancel_run _force_close error (ignored): %s", exc)
    if ctx and ctx.agent_task and not ctx.agent_task.done():
        ctx.agent_task.cancel()
        logger.info("Cancelled agent_task for run %s on thread %s", run_id, thread_id)
    logger.info("Cancelled run %s on thread %s", run_id, thread_id)
    return True


def cancel_all_for_thread(thread_id: str) -> int:
    """Cancel every active run on *thread_id*.  Returns the count cancelled."""
    count = 0
    for (tid, rid), evt in list(_active_runs.items()):
        if tid == thread_id:
            evt.set()
            count += 1
            logger.info("Cancelled run %s on thread %s (bulk)", rid, tid)
    return count


def unregister_run(thread_id: str, run_id: str) -> None:
    """Remove a finished / cancelled run from the registry."""
    logger.debug("Unregister called for thread_id=%s, run_id=%s", thread_id, run_id)
    _active_runs.pop((thread_id, run_id), None)
    _run_contexts.pop((thread_id, run_id), None)
    logger.debug("Unregistered run %s on thread %s", run_id, thread_id)


def is_cancelled(thread_id: str, run_id: str) -> bool:
    """Check whether a run has been cancelled."""
    evt = _active_runs.get((thread_id, run_id))
    return evt is not None and evt.is_set()
