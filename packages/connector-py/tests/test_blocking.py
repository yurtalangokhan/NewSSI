"""Blocking iterators drained in a worker thread: what happens when the consumer leaves."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator

import pytest

from connector.common.blocking import iterate_in_thread


async def test_a_cancelled_read_waits_for_the_chunk_the_worker_is_fetching() -> None:
    fetching, answer = threading.Event(), threading.Event()
    closed: list[str] = []
    got: list[int] = []

    def rows() -> Iterator[int]:
        try:
            for i in range(10):
                if i == 3:
                    fetching.set()
                    answer.wait(5)  # a slow fetch on the server: the thread cannot be interrupted
                yield i
        finally:
            closed.append("cursor")

    cursor = rows()

    async def read() -> None:
        try:
            async for item in iterate_in_thread(cursor, chunk_size=2):
                got.append(item)
        finally:
            # What the sources do with the cursor they opened.
            await asyncio.to_thread(cursor.close)

    reading = asyncio.create_task(read())
    try:
        await asyncio.to_thread(fetching.wait, 5)
        reading.cancel()
        await asyncio.sleep(0.05)
        # The worker is still inside the iterator. Closing it now is "generator already
        # executing", which would replace the cancellation with a failure.
        assert not reading.done()
    finally:
        answer.set()

    with pytest.raises(asyncio.CancelledError):
        await reading
    assert got == [0, 1] and closed == ["cursor"]


async def test_a_consumer_that_stops_early_leaves_the_iterator_closed() -> None:
    state = {"pulled": 0, "closed": False}

    def rows() -> Iterator[int]:
        try:
            for i in range(10_000):
                state["pulled"] += 1
                yield i
        finally:
            state["closed"] = True

    cursor = rows()  # still referenced by its owner: only an explicit close ends it
    items = iterate_in_thread(cursor, chunk_size=100)
    async for item in items:
        if item == 5:
            break
    await items.aclose()

    assert state == {"pulled": 100, "closed": True}
