import asyncio
from contextvars import ContextVar

import pytest

from service.AgentStreamService import _Heartbeat, _with_idle_heartbeat


@pytest.mark.asyncio
async def test_stream_context_survives_yields_and_is_reset_in_its_own_task():
    identity = ContextVar("test_stream_identity", default=None)
    observations = []

    async def source():
        token = identity.set("assigned-agent-user")
        try:
            observations.append(identity.get())
            yield "first"
            observations.append(identity.get())
            yield "second"
        finally:
            identity.reset(token)
            observations.append(identity.get())

    assert [item async for item in _with_idle_heartbeat(source(), 0.01)] == ["first", "second"]
    assert observations == ["assigned-agent-user", "assigned-agent-user", None]
    assert identity.get() is None


@pytest.mark.asyncio
async def test_source_cancellation_propagates_instead_of_heartbeating_forever():
    async def source():
        yield "first"
        raise asyncio.CancelledError()

    async def consume():
        return [item async for item in _with_idle_heartbeat(source(), 0.001)]

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(consume(), timeout=0.1)


@pytest.mark.asyncio
async def test_heartbeats_do_not_cancel_or_restart_quiet_source():
    release = asyncio.Event()
    starts = 0

    async def source():
        nonlocal starts
        starts += 1
        await release.wait()
        yield "ready"

    stream = _with_idle_heartbeat(source(), 0.001)
    try:
        assert isinstance(await anext(stream), _Heartbeat)
        assert isinstance(await anext(stream), _Heartbeat)
        release.set()
        assert [item async for item in stream if not isinstance(item, _Heartbeat)] == ["ready"]
        assert starts == 1
    finally:
        await stream.aclose()


@pytest.mark.asyncio
async def test_stream_error_is_raised_after_preceding_data_and_cleanup():
    cleaned = False

    async def source():
        nonlocal cleaned
        try:
            yield "first"
            raise RuntimeError("connector failed")
        finally:
            cleaned = True

    stream = _with_idle_heartbeat(source(), 0.01)
    assert await anext(stream) == "first"
    with pytest.raises(RuntimeError, match="connector failed"):
        await anext(stream)
    assert cleaned


@pytest.mark.asyncio
async def test_closing_consumer_closes_source_in_original_context():
    identity = ContextVar("cancel_stream_identity", default=None)
    closed = asyncio.Event()

    async def source():
        token = identity.set("user-one")
        try:
            yield "first"
            await asyncio.Event().wait()
        finally:
            identity.reset(token)
            closed.set()

    stream = _with_idle_heartbeat(source(), 0.001)
    assert await anext(stream) == "first"
    await stream.aclose()
    assert closed.is_set()
    assert identity.get() is None


@pytest.mark.asyncio
async def test_close_does_not_hang_when_cleanup_fails_with_full_buffer():
    buffered = asyncio.Event()
    closed = asyncio.Event()

    async def source():
        try:
            yield "first"
            yield "buffered"
            buffered.set()
            yield "blocked"
        finally:
            closed.set()
            raise RuntimeError("cleanup failed")

    stream = _with_idle_heartbeat(source(), 0.001)
    assert await anext(stream) == "first"
    await buffered.wait()
    await asyncio.wait_for(stream.aclose(), timeout=0.1)
    assert closed.is_set()
