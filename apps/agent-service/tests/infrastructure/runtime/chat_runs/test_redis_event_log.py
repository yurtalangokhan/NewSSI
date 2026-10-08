import pytest

from infrastructure.runtime.chat_runs.keys import events_key
from infrastructure.runtime.chat_runs.redis_event_log import RedisRunEventLog
from tests.service.chat_runs.event_log_contract import EventLogContract

pytestmark = pytest.mark.asyncio


class TestRedisRunEventLog(EventLogContract):
    @pytest.fixture
    def make_log(self, redis_client):
        # Exact trimming keeps the trim contract deterministic; production uses `~`.
        return lambda max_events=50_000: RedisRunEventLog(
            redis_client, max_events=max_events, approximate_trim=False
        )


async def test_ids_are_the_sequence_numbers(redis_client):
    log = RedisRunEventLog(redis_client, max_events=100)
    await log.append("r1", 1, "a")
    await log.append("r1", 2, "b")
    entries = await redis_client.xrange(events_key("r1"))
    assert [entry_id for entry_id, _ in entries] == ["0-1", "0-2"]


async def test_expire_sets_a_ttl_on_the_stream(redis_client):
    log = RedisRunEventLog(redis_client, max_events=100)
    await log.append("r1", 1, "a")
    await log.expire("r1", 600)
    assert 0 < await redis_client.ttl(events_key("r1")) <= 600


class _CountingClient:
    """Counts round trips: each direct command or pipeline execute is one."""

    def __init__(self, client) -> None:
        self._client = client
        self.round_trips = 0

    def pipeline(self, transaction: bool = True):
        pipe = self._client.pipeline(transaction=transaction)
        original = pipe.execute

        async def execute(*args, **kwargs):
            self.round_trips += 1
            return await original(*args, **kwargs)

        pipe.execute = execute
        return pipe

    def __getattr__(self, name):
        attr = getattr(self._client, name)
        if not callable(attr):
            return attr

        async def call(*args, **kwargs):
            self.round_trips += 1
            return await attr(*args, **kwargs)

        return call


async def test_concurrent_appends_from_many_runs_share_round_trips(redis_client):
    # Every token is one XADD; a replica streaming many runs at once would
    # spend its CPU on per-command overhead. Appends that arrive while one
    # batch is in flight go out together in the next pipeline.
    import asyncio

    counting = _CountingClient(redis_client)
    log = RedisRunEventLog(counting, max_events=100)
    try:

        async def run(run_id: str) -> None:
            for seq in range(1, 11):
                await log.append(run_id, seq, f"{run_id}-{seq}")

        await asyncio.gather(*(run(f"r{i}") for i in range(50)))

        assert counting.round_trips < 50 * 10 / 5
        for i in (0, 49):
            entries = await redis_client.xrange(events_key(f"r{i}"))
            assert [fields["d"] for _, fields in entries] == [f"r{i}-{seq}" for seq in range(1, 11)]
    finally:
        await log.aclose()


async def test_a_fenced_append_fails_only_its_own_run(redis_client):
    import asyncio

    from service.chat_runs.domain import EventSequenceError

    log = RedisRunEventLog(redis_client, max_events=100)
    try:
        await log.append("zombie", 1, "a")
        results = await asyncio.gather(
            log.append("zombie", 1, "again"), log.append("healthy", 1, "b"), return_exceptions=True
        )
        assert isinstance(results[0], EventSequenceError)
        assert results[1] is None
    finally:
        await log.aclose()


async def test_concurrent_reads_share_round_trips(redis_client):
    import asyncio

    log = RedisRunEventLog(redis_client, max_events=100)
    for i in range(30):
        await log.append(f"r{i}", 1, "x")
    counting = _CountingClient(redis_client)
    reader_log = RedisRunEventLog(counting, max_events=100)
    try:
        pages = await asyncio.gather(*(reader_log.read_after(f"r{i}", 0) for i in range(30)))
        assert all(len(page) == 1 for page in pages)
        assert counting.round_trips < 30 / 3
    finally:
        await log.aclose()
        await reader_log.aclose()
