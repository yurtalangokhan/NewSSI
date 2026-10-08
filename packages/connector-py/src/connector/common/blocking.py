"""Blocking client libraries inside an event loop.

boto3, pyodbc, the Spark clients and friends block the calling thread. A sync
runs in the same process as everything else the host serves, so their calls
are pushed to a worker thread.
"""

from __future__ import annotations

import asyncio
import itertools
from collections.abc import AsyncIterator, Iterator
from typing import Any, TypeVar

T = TypeVar("T")


async def iterate_in_thread(iterator: Iterator[T], chunk_size: int = 500) -> AsyncIterator[T]:
    """Drain ``iterator`` in a worker thread, ``chunk_size`` items per hop.

    For iterators that do I/O as they advance: rows parsed lazily from a network
    stream, a driver cursor. Memory stays bounded by one chunk.

    The iterator is only ever touched by one thread at a time. A consumer that is
    cancelled while a chunk is being fetched waits for that fetch: the thread
    cannot be interrupted, and closing an iterator another thread is advancing
    fails. Whichever way the consumer leaves, the iterator is closed.
    """

    def take() -> list[T]:
        return list(itertools.islice(iterator, chunk_size))

    try:
        while True:
            fetch = asyncio.ensure_future(asyncio.to_thread(take))
            try:
                chunk = await asyncio.shield(fetch)
            except asyncio.CancelledError:
                await _settled(fetch)
                raise
            if not chunk:
                return
            for item in chunk:
                yield item
    finally:
        close = getattr(iterator, "close", None)
        if close is not None:
            await asyncio.to_thread(close)


async def _settled(fetch: asyncio.Future[Any]) -> None:
    """Wait until ``fetch`` is over, whatever it ended with, however often we are cancelled."""
    while not fetch.done():
        try:
            await asyncio.wait({fetch})
        except asyncio.CancelledError:
            continue
    if not fetch.cancelled():
        fetch.exception()  # looked at, so asyncio does not report it as never retrieved
