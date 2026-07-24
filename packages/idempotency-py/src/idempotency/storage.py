import asyncio

import redis.asyncio as aioredis

from idempotency.models import CachedResponse

_RESPONSE_KEY_PREFIX = "idem"
_LOCK_SUFFIX = "lock"


def _response_key(service: str, idem_key: str) -> str:
    return f"{_RESPONSE_KEY_PREFIX}:{service}:{idem_key}"


def _lock_key(service: str, idem_key: str) -> str:
    return f"{_RESPONSE_KEY_PREFIX}:{service}:{idem_key}:{_LOCK_SUFFIX}"


async def get_cached_response(
    redis: aioredis.Redis,
    service: str,
    idem_key: str,
) -> CachedResponse | None:
    raw = await redis.get(_response_key(service, idem_key))
    if raw is None:
        return None
    return CachedResponse.model_validate_json(raw)


async def set_cached_response(
    redis: aioredis.Redis,
    service: str,
    idem_key: str,
    response: CachedResponse,
    ttl: int,
) -> None:
    await redis.setex(
        _response_key(service, idem_key),
        ttl,
        response.model_dump_json(),
    )


async def acquire_lock(
    redis: aioredis.Redis,
    service: str,
    idem_key: str,
    lock_ttl: int = 10,
) -> bool:
    result = await redis.setnx(_lock_key(service, idem_key), "1")
    if result:
        await redis.expire(_lock_key(service, idem_key), lock_ttl)
        return True
    return False


async def release_lock(
    redis: aioredis.Redis,
    service: str,
    idem_key: str,
) -> None:
    await redis.delete(_lock_key(service, idem_key))


async def wait_for_lock_and_get(
    redis: aioredis.Redis,
    service: str,
    idem_key: str,
    poll_interval: float = 0.1,
    max_wait: float = 10.0,
) -> CachedResponse | None:
    elapsed = 0.0
    while elapsed < max_wait:
        cached = await get_cached_response(redis, service, idem_key)
        if cached is not None:
            return cached
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
    return None
