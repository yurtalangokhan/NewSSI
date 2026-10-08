"""Spec: memory-extraction background tasks must not grow unbounded or hang
forever. Before this, `spawn_tracked` put a coroutine straight onto the event
loop with no concurrency cap and no timeout on the LLM call inside it, so a
slow model or a burst of concurrent turns could pile up outstanding tasks and
a single stuck LLM call could never be reclaimed.
"""

import asyncio

import pytest
from langchain_core.messages import HumanMessage

import memory.long_term as lt


async def _drain_background_tasks() -> None:
    if lt._BACKGROUND_TASKS:
        await asyncio.gather(*list(lt._BACKGROUND_TASKS), return_exceptions=True)


class _ConcurrencyCounter:
    def __init__(self) -> None:
        self.current = 0
        self.peak = 0
        self.lock = asyncio.Lock()


class _BoundBlocking:
    def __init__(self, counter: _ConcurrencyCounter, release: asyncio.Event) -> None:
        self._counter = counter
        self._release = release

    async def ainvoke(self, messages, config=None):
        async with self._counter.lock:
            self._counter.current += 1
            self._counter.peak = max(self._counter.peak, self._counter.current)
        await self._release.wait()
        async with self._counter.lock:
            self._counter.current -= 1
        return lt.ExtractedFacts(facts=[])


class _BlockingModel:
    """Blocks inside ainvoke until released, tracking how many calls overlap."""

    def __init__(self, counter: _ConcurrencyCounter, release: asyncio.Event) -> None:
        self._counter = counter
        self._release = release

    def with_structured_output(self, schema):
        return _BoundBlocking(self._counter, self._release)


class _BoundNeverResponding:
    async def ainvoke(self, messages, config=None):
        await asyncio.Event().wait()


class _NeverRespondingModel:
    """Never returns from ainvoke -- simulates a stuck LLM call."""

    def with_structured_output(self, schema):
        return _BoundNeverResponding()


@pytest.mark.asyncio
async def test_extraction_never_exceeds_the_concurrency_cap(monkeypatch):
    monkeypatch.setattr(lt, "_EXTRACTION_SEMAPHORE", asyncio.Semaphore(2))

    counter = _ConcurrencyCounter()
    release = asyncio.Event()
    messages = [HumanMessage(content="hi")]

    for _ in range(5):
        await lt.extract_and_save_memories(
            "user-1", messages, _BlockingModel(counter, release)
        )

    # Let every spawned task reach (or block on) the semaphore.
    await asyncio.sleep(0.05)
    # peak == 0 would mean the fake was never actually invoked (e.g. the
    # call silently failed before reaching the LLM call) -- assert the cap
    # was both hit and respected, not just "never exceeded".
    assert counter.peak == 2

    release.set()
    await asyncio.wait_for(_drain_background_tasks(), timeout=1.0)


@pytest.mark.asyncio
async def test_extraction_times_out_instead_of_hanging_forever(monkeypatch):
    monkeypatch.setattr(lt, "EXTRACTION_TIMEOUT_SECONDS", 0.05)
    messages = [HumanMessage(content="hi")]

    await lt.extract_and_save_memories("user-1", messages, _NeverRespondingModel())

    # If the LLM call weren't bounded by a timeout, this would hang until the
    # outer wait_for gives up -- proving the task never completes on its own.
    await asyncio.wait_for(_drain_background_tasks(), timeout=1.0)
