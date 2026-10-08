import asyncio

import pytest

from infrastructure.runtime.chat_runs.wiring import new_instance_id, start_chat_runs, stop_chat_runs
from service.chat.session_naming_service import get_naming_lock
from service.chat_runs import provider
from service.chat_runs.domain import ChatRunSpec, ChatRunUnavailableError
from tests.service.chat_runs.fakes import fast_settings, frames_of, wait_terminal

pytestmark = pytest.mark.asyncio


async def test_runtime_runs_end_to_end_on_redis_and_tears_down(redis_client):
    runtime = start_chat_runs(redis_client, settings=fast_settings(), instance_id=new_instance_id())
    try:
        assert provider.get_chat_run_service() is runtime.service
        assert type(get_naming_lock()).__name__ == "RedisNamingLock"
        run = await runtime.service.start(
            ChatRunSpec(thread_id="t1", owner_user_id="u1"), frames_of('{"type": "token"}')
        )
        registry = runtime.supervisor._registry  # noqa: SLF001
        assert (await wait_terminal(registry, run.run_id)).status.value == "completed"
    finally:
        await stop_chat_runs(runtime)
    with pytest.raises(ChatRunUnavailableError):
        provider.get_chat_run_service()


def test_instance_ids_are_unique():
    assert new_instance_id() != new_instance_id()


async def test_chat_runs_get_their_own_waiting_pools_for_writes_and_reads(redis_client):
    # Viewers must never exhaust the connections that write tokens and renew
    # leases, and none of them may share the idempotency pool.
    from redis.asyncio import BlockingConnectionPool

    runtime = start_chat_runs(redis_client, settings=fast_settings(), instance_id=new_instance_id())
    try:
        writer, reader = runtime.writer_client, runtime.reader_client
        pools = {id(redis_client.connection_pool), id(writer.connection_pool), id(reader.connection_pool)}
        assert len(pools) == 3
        assert isinstance(writer.connection_pool, BlockingConnectionPool)
        assert isinstance(reader.connection_pool, BlockingConnectionPool)
    finally:
        await stop_chat_runs(runtime)


async def test_many_viewers_share_a_small_pool_without_errors(redis_client):
    # Readers poll instead of blocking, so a handful of connections serves
    # many open streams.
    from infrastructure.runtime.chat_runs import wiring

    runtime = start_chat_runs(
        redis_client, settings=fast_settings(), instance_id=new_instance_id(), reader_pool_size=2
    )
    try:
        run = await runtime.service.start(
            ChatRunSpec(thread_id="t1", owner_user_id="u1"), frames_of('{"type": "token"}', delay=0.2)
        )

        async def view():
            frames = [f async for f in await runtime.service.open_events(run.run_id, after_seq=0, owner_ids={"u1"})]
            return frames[-1]

        results = await asyncio.gather(*(view() for _ in range(20)))
        assert all(last.endswith("data: [DONE]\n\n") for last in results)
        assert wiring.READER_POOL_SIZE >= 50
    finally:
        await stop_chat_runs(runtime)
