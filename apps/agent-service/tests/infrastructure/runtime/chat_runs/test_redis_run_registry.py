import pytest

from infrastructure.runtime.chat_runs.keys import run_key
from infrastructure.runtime.chat_runs.redis_run_registry import RedisRunRegistry
from tests.service.chat_runs.run_registry_contract import RunRegistryContract, make_run

pytestmark = pytest.mark.asyncio


class TestRedisRunRegistry(RunRegistryContract):
    @pytest.fixture
    def registry(self, redis_client):
        return RedisRunRegistry(redis_client)


async def test_expire_sets_a_ttl_on_the_run_hash(redis_client):
    registry = RedisRunRegistry(redis_client)
    await registry.try_acquire(make_run("r1"), lease_ttl_seconds=5)
    await registry.expire("r1", 600)
    assert 0 < await redis_client.ttl(run_key("r1")) <= 600


async def test_acquire_gives_the_run_hash_a_ttl_atomically(redis_client):
    # A run whose start or finalization fails half-way must never leave its
    # hash (with the user's input preview) behind forever.
    registry = RedisRunRegistry(redis_client)
    await registry.try_acquire(make_run("r1"), lease_ttl_seconds=5, run_ttl_seconds=4200)
    assert 4000 < await redis_client.ttl(run_key("r1")) <= 4200
