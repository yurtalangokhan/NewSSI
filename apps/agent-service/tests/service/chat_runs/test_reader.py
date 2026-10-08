import asyncio
import json

import pytest

from service.chat_runs.domain import RunStatus
from service.chat_runs.frames import HEARTBEAT_FRAME, caught_up_payload, format_unsequenced
from service.chat_runs.reader import RunEventReader
from tests.service.chat_runs.fakes import (
    FakeClock,
    InMemoryRunEventLog,
    InMemoryRunRegistry,
    fast_settings,
)
from tests.service.chat_runs.run_registry_contract import make_run

pytestmark = pytest.mark.asyncio

CAUGHT_UP_FRAME = format_unsequenced(caught_up_payload())


async def _setup(max_events=50_000, clock=None, **settings):
    registry, log = InMemoryRunRegistry(), InMemoryRunEventLog(max_events=max_events)
    await registry.try_acquire(make_run("r1"), lease_ttl_seconds=30)
    reader = RunEventReader(
        registry=registry,
        event_log=log,
        settings=fast_settings(**settings),
        clock=clock,
        poll_interval_seconds=0.02,
    )
    return reader, registry, log


async def _complete(log, start, tokens):
    seq = start
    for token in tokens:
        seq += 1
        await log.append("r1", seq, json.dumps({"type": "token", "content": token}))
    await log.append("r1", seq + 1, '{"type": "run_end", "status": "completed", "error_code": null}')
    await log.append("r1", seq + 2, "[DONE]")


async def _collect(stream, limit=100):
    frames = []
    async for frame in stream:
        frames.append(frame)
        if len(frames) >= limit:
            break
    return frames


def _ids(frames):
    return [int(f.split("\n", 1)[0][4:]) for f in frames if f.startswith("id: ")]


async def test_replays_from_zero_and_closes_after_done():
    reader, _, log = await _setup()
    await log.append("r1", 1, '{"type": "run_started"}')
    await _complete(log, 1, ["a", "b"])
    frames = await _collect(reader.stream("r1", 0))
    assert _ids(frames) == [1, 2, 3, 4, 5]
    assert frames[-1] == "id: 5\ndata: [DONE]\n\n"


async def test_starts_strictly_after_the_given_seq():
    reader, _, log = await _setup()
    await log.append("r1", 1, '{"type": "run_started"}')
    await _complete(log, 1, ["a", "b"])
    assert _ids(await _collect(reader.stream("r1", 3))) == [4, 5]


async def test_tail_after_replay_has_no_gap_or_duplicate():
    reader, _, log = await _setup()
    await log.append("r1", 1, '{"type": "run_started"}')
    await log.append("r1", 2, '{"type": "token", "content": "a"}')

    async def produce_later():
        await asyncio.sleep(0.1)
        await _complete(log, 2, ["b", "c"])

    producer = asyncio.create_task(produce_later())
    frames = await _collect(reader.stream("r1", 0))
    await producer
    assert _ids(frames) == [1, 2, 3, 4, 5, 6]


async def test_two_readers_see_identical_sequences():
    reader, _, log = await _setup()
    await log.append("r1", 1, '{"type": "run_started"}')
    first = asyncio.create_task(_collect(reader.stream("r1", 0)))
    second = asyncio.create_task(_collect(reader.stream("r1", 0)))
    await asyncio.sleep(0.05)
    await _complete(log, 1, ["a", "b", "c"])
    assert await first == await second


async def test_emits_heartbeats_while_idle():
    reader, _, log = await _setup(sse_heartbeat_seconds=0.1)
    await log.append("r1", 1, '{"type": "run_started"}')
    stream = reader.stream("r1", 1)
    assert await asyncio.wait_for(stream.__anext__(), 1.0) == CAUGHT_UP_FRAME
    frame = await asyncio.wait_for(stream.__anext__(), 1.0)
    await stream.aclose()
    assert frame == HEARTBEAT_FRAME


async def test_trimmed_position_sends_resync_without_an_id_and_closes():
    reader, _, log = await _setup(max_events=3)
    await log.append("r1", 1, '{"type": "run_started"}')
    await _complete(log, 1, ["a", "b", "c"])
    frames = await _collect(reader.stream("r1", 0))
    # seqs 1..6 were written (started, a, b, c, run_end, DONE); max 3 keeps 4..6
    assert frames == ['data: {"type": "resync", "first_available_seq": 4}\n\n']


async def test_terminal_run_without_run_end_gets_a_synthetic_end():
    clock = FakeClock()
    reader, registry, log = await _setup(clock=clock)
    await log.append("r1", 1, '{"type": "run_started"}')
    await registry.mark_terminal("r1", RunStatus.FAILED, error_code="x", finished_at=clock.now())
    clock.advance(1.0)  # past 2 x heartbeat: the writer is not coming back
    frames = await _collect(reader.stream("r1", 1))
    assert json.loads(frames[0][6:]) == {"type": "run_end", "status": "failed", "error_code": "x"}
    assert frames[-1] == "data: [DONE]\n\n"


def _run_end_frames(frames):
    return [f for f in frames if '"run_end"' in f]


async def _terminal_with_run_end_but_no_done(clock):
    reader, registry, log = await _setup(clock=clock)
    await log.append("r1", 1, '{"type": "run_started"}')
    await log.append("r1", 2, '{"type": "run_end", "status": "completed", "error_code": null}')
    await registry.mark_terminal("r1", RunStatus.COMPLETED, error_code=None, finished_at=clock.now())
    clock.advance(1.0)
    return reader


async def test_a_run_end_already_in_the_log_is_not_repeated_before_done():
    reader = await _terminal_with_run_end_but_no_done(FakeClock())
    frames = await _collect(reader.stream("r1", 0))
    assert len(_run_end_frames(frames)) == 1
    assert frames[-1] == "data: [DONE]\n\n"


async def test_a_client_resuming_past_the_run_end_only_gets_done():
    reader = await _terminal_with_run_end_but_no_done(FakeClock())
    frames = await _collect(reader.stream("r1", 2))
    assert frames == ["data: [DONE]\n\n"]


async def test_expired_meta_gets_a_synthetic_end():
    reader, _, log = await _setup()
    frames = await _collect(reader.stream("missing", 0))
    assert json.loads(frames[0][6:])["error_code"] == "run_expired"
    assert frames[-1] == "data: [DONE]\n\n"


async def test_an_idle_reader_never_holds_a_blocking_read():
    # A blocking XREAD pins a pooled Redis connection per open stream; readers
    # poll with short sleeps instead.
    reader, _, log = await _setup()
    blocks: list[float] = []
    original = log.read_after

    async def spy(run_id, after_seq, *, block_seconds=0.0, limit=500):
        blocks.append(block_seconds)
        return await original(run_id, after_seq, block_seconds=block_seconds, limit=limit)

    log.read_after = spy
    stream = reader.stream("r1", 0)
    pending = asyncio.ensure_future(stream.__anext__())
    await asyncio.sleep(0.2)
    await log.append("r1", 1, '{"type": "token", "content": "a"}')
    assert await asyncio.wait_for(pending, 1.0) == CAUGHT_UP_FRAME
    first = await asyncio.wait_for(stream.__anext__(), 1.0)
    while first == HEARTBEAT_FRAME:
        first = await asyncio.wait_for(stream.__anext__(), 1.0)
    await stream.aclose()

    assert first.startswith("id: 1\n")
    assert blocks and set(blocks) == {0.0}


async def _frames_until(stream, count):
    frames = []
    while len(frames) < count:
        frames.append(await asyncio.wait_for(stream.__anext__(), 2.0))
    return frames


async def test_caught_up_follows_the_replay_and_precedes_live_events():
    reader, _, log = await _setup()
    await log.append("r1", 1, '{"type": "run_started"}')
    await log.append("r1", 2, '{"type": "token", "content": "a"}')
    stream = reader.stream("r1", 0)
    replayed = await _frames_until(stream, 3)
    assert _ids(replayed) == [1, 2]
    assert replayed[2] == CAUGHT_UP_FRAME

    await log.append("r1", 3, '{"type": "token", "content": "b"}')
    live = await _frames_until(stream, 1)
    await stream.aclose()
    assert _ids(live) == [3]


async def test_caught_up_is_sent_exactly_once_per_stream():
    reader, _, log = await _setup(sse_heartbeat_seconds=0.05)
    await log.append("r1", 1, '{"type": "run_started"}')

    async def produce_later():
        await asyncio.sleep(0.15)
        await _complete(log, 1, ["a"])

    producer = asyncio.create_task(produce_later())
    frames = await _collect(reader.stream("r1", 0))
    await producer
    assert frames.count(CAUGHT_UP_FRAME) == 1


async def test_caught_up_is_sent_at_once_when_nothing_is_left_to_replay():
    reader, _, log = await _setup()
    await log.append("r1", 1, '{"type": "run_started"}')
    stream = reader.stream("r1", 1)
    first = await asyncio.wait_for(stream.__anext__(), 1.0)
    await stream.aclose()
    assert first == CAUGHT_UP_FRAME


async def test_a_replay_that_reaches_done_never_goes_idle_so_no_caught_up():
    reader, _, log = await _setup()
    await log.append("r1", 1, '{"type": "run_started"}')
    await _complete(log, 1, ["a", "b"])
    frames = await _collect(reader.stream("r1", 0))
    assert CAUGHT_UP_FRAME not in frames


async def test_a_trimmed_position_gets_resync_and_no_caught_up():
    reader, _, log = await _setup(max_events=3)
    await log.append("r1", 1, '{"type": "run_started"}')
    await _complete(log, 1, ["a", "b", "c"])
    frames = await _collect(reader.stream("r1", 0))
    assert CAUGHT_UP_FRAME not in frames


async def test_a_dead_writer_gets_the_synthetic_end_and_no_caught_up():
    clock = FakeClock()
    reader, registry, log = await _setup(clock=clock)
    await log.append("r1", 1, '{"type": "run_started"}')
    await registry.mark_terminal("r1", RunStatus.FAILED, error_code="x", finished_at=clock.now())
    clock.advance(1.0)
    frames = await _collect(reader.stream("r1", 1))
    assert CAUGHT_UP_FRAME not in frames


async def test_caught_up_carries_no_sequence_id():
    reader, _, log = await _setup()
    await log.append("r1", 1, '{"type": "run_started"}')
    stream = reader.stream("r1", 1)
    frame = await asyncio.wait_for(stream.__anext__(), 1.0)
    await stream.aclose()
    assert not frame.startswith("id:")
    assert json.loads(frame[6:]) == {"type": "caught_up"}
