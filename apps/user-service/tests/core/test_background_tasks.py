"""Spec: fire-and-forget work (syncing a memory fact to rag-service) must
not be garbage-collected mid-flight, and must be reachable for graceful
shutdown. Mirrors agent-service's memory/long_term.py spawn_tracked, the
same pattern already proven there for background extraction tasks.
"""

import asyncio

import pytest

from src.core.background_tasks import (
    _BACKGROUND_TASKS,
    cancel_all_background_tasks,
    spawn_tracked,
)


@pytest.fixture(autouse=True)
def _clear_tasks():
    _BACKGROUND_TASKS.clear()
    yield
    _BACKGROUND_TASKS.clear()


@pytest.mark.asyncio
async def test_spawn_tracked_runs_the_coroutine():
    ran = False

    async def _work():
        nonlocal ran
        ran = True

    spawn_tracked(_work())
    await asyncio.sleep(0)

    assert ran is True


@pytest.mark.asyncio
async def test_spawn_tracked_holds_a_reference_until_done():
    release = asyncio.Event()

    async def _work():
        await release.wait()

    spawn_tracked(_work())
    await asyncio.sleep(0)

    assert len(_BACKGROUND_TASKS) == 1

    release.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert len(_BACKGROUND_TASKS) == 0


@pytest.mark.asyncio
async def test_cancel_all_background_tasks_cancels_everything_tracked():
    started = asyncio.Event()
    cancelled = False

    async def _work():
        nonlocal cancelled
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled = True
            raise

    spawn_tracked(_work())
    await started.wait()

    await cancel_all_background_tasks()

    assert cancelled is True
    assert len(_BACKGROUND_TASKS) == 0


@pytest.mark.asyncio
async def test_cancel_all_background_tasks_is_a_noop_with_nothing_tracked():
    await cancel_all_background_tasks()
