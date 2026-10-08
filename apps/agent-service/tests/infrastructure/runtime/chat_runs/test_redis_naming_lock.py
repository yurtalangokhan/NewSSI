import asyncio

import pytest

from infrastructure.runtime.chat_runs.redis_naming_lock import RedisNamingLock
from service.chat.session_naming_service import LocalNamingLock

pytestmark = pytest.mark.asyncio


@pytest.fixture(params=["redis", "local"])
def lock(request, redis_client):
    return RedisNamingLock(redis_client, ttl_seconds=1) if request.param == "redis" else LocalNamingLock(ttl_seconds=1)


async def test_acquire_is_exclusive_and_release_is_token_checked(lock):
    token = await lock.acquire("t1")
    assert token and await lock.acquire("t1") is None and await lock.is_held("t1")
    await lock.release("t1", "not-mine")
    assert await lock.is_held("t1")
    await lock.release("t1", token)
    assert not await lock.is_held("t1")


async def test_a_crashed_holder_expires(lock):
    assert await lock.acquire("t1")
    await asyncio.sleep(1.2)
    assert await lock.acquire("t1")
