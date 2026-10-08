"""Cross-instance naming lock: SET NX EX with a compare-and-delete release."""

from __future__ import annotations

import uuid

from redis.asyncio import Redis

from infrastructure.runtime.chat_runs.keys import naming_lock_key

_RELEASE_NAMING_LOCK = """
if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end
return 0
"""


class RedisNamingLock:
    def __init__(self, client: Redis, *, ttl_seconds: int = 30) -> None:
        self._client = client
        self._ttl = ttl_seconds
        self._release = client.register_script(_RELEASE_NAMING_LOCK)

    async def acquire(self, thread_id: str) -> str | None:
        token = uuid.uuid4().hex
        ok = await self._client.set(naming_lock_key(thread_id), token, nx=True, ex=self._ttl)
        return token if ok else None

    async def release(self, thread_id: str, token: str) -> None:
        await self._release(keys=[naming_lock_key(thread_id)], args=[token])

    async def is_held(self, thread_id: str) -> bool:
        return bool(await self._client.exists(naming_lock_key(thread_id)))
