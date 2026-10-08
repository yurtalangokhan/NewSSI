"""Tracked fire-and-forget background tasks.

Mirrors agent-service's memory/long_term.py spawn_tracked: a bare
``asyncio.create_task(...)`` has nothing holding a reference to it once
the caller returns, so it can be garbage-collected mid-flight, and nothing
can reach it to cancel cleanly at shutdown. Tracking it here fixes both.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

_BACKGROUND_TASKS: set[asyncio.Task] = set()


def spawn_tracked(coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
    """Schedule a coroutine as a tracked background task."""
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return task


async def cancel_all_background_tasks() -> None:
    """Cancel every tracked background task and await cleanup."""
    for task in list(_BACKGROUND_TASKS):
        task.cancel()
    if _BACKGROUND_TASKS:
        await asyncio.gather(*_BACKGROUND_TASKS, return_exceptions=True)
