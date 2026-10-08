"""Behaviour every RunEventLog adapter must share. Subclass and provide `make_log`."""

import asyncio
import time

import pytest

from service.chat_runs.domain import EventSequenceError, ReplayWindowExpiredError


class EventLogContract:
    @pytest.fixture
    def make_log(self):  # pragma: no cover - overridden
        raise NotImplementedError

    async def _fill(self, log, run_id: str, last: int) -> None:
        for seq in range(1, last + 1):
            await log.append(run_id, seq, f"p{seq}")

    async def test_reads_events_strictly_after_the_given_seq(self, make_log):
        log = make_log()
        await self._fill(log, "r1", 3)
        assert [e.seq for e in await log.read_after("r1", 1)] == [2, 3]
        assert [e.payload for e in await log.read_after("r1", 0)] == ["p1", "p2", "p3"]

    async def test_limit_caps_a_page_in_order(self, make_log):
        log = make_log()
        await self._fill(log, "r1", 10)
        assert [e.seq for e in await log.read_after("r1", 0, limit=4)] == [1, 2, 3, 4]

    async def test_rejects_a_seq_that_is_not_above_the_last(self, make_log):
        log = make_log()
        await log.append("r1", 1, "a")
        with pytest.raises(EventSequenceError):
            await log.append("r1", 1, "b")

    async def test_runs_are_isolated(self, make_log):
        log = make_log()
        await log.append("r1", 1, "a")
        assert await log.read_after("r2", 0) == []
        assert await log.last_seq("r2") == 0

    async def test_block_returns_empty_after_the_timeout(self, make_log):
        log = make_log()
        started = time.monotonic()
        assert await log.read_after("r1", 0, block_seconds=0.2) == []
        assert time.monotonic() - started >= 0.15

    async def test_block_wakes_on_append(self, make_log):
        log = make_log()
        reader = asyncio.create_task(log.read_after("r1", 0, block_seconds=1.5))
        await asyncio.sleep(0.05)
        started = time.monotonic()
        await log.append("r1", 1, "late")
        events = await reader
        assert [e.payload for e in events] == ["late"]
        assert time.monotonic() - started < 1.0

    async def test_trimmed_position_raises_with_the_first_available_seq(self, make_log):
        log = make_log(max_events=3)
        await self._fill(log, "r1", 5)
        with pytest.raises(ReplayWindowExpiredError) as exc:
            await log.read_after("r1", 0)
        assert exc.value.first_seq == 3
        assert [e.seq for e in await log.read_after("r1", 2)] == [3, 4, 5]

    async def test_last_seq_survives_trimming(self, make_log):
        log = make_log(max_events=3)
        await self._fill(log, "r1", 5)
        assert await log.last_seq("r1") == 5
        with pytest.raises(EventSequenceError):
            await log.append("r1", 5, "dup")

    async def test_expire_keeps_events_readable(self, make_log):
        log = make_log()
        await self._fill(log, "r1", 2)
        await log.expire("r1", 600)
        assert [e.seq for e in await log.read_after("r1", 0)] == [1, 2]
