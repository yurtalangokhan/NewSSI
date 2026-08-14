import asyncio
import uuid
from enum import StrEnum

import redis.asyncio as aioredis

from idempotency.models import CachedResponse, IdempotencyKeyOwner

_RESPONSE_KEY_PREFIX = "idem"
_LOCK_SUFFIX = "lock"
_RESPONSE_SUFFIX = "response"
_OWNER_SUFFIX = "owner"


class ClaimKeyOwnerResult(StrEnum):
    CREATED = "created"
    EXISTING_COMPATIBLE = "existing_compatible"
    CONFLICT = "conflict"


def _response_key(service: str, principal_scope: str, idem_key: str) -> str:
    return (
        f"{_RESPONSE_KEY_PREFIX}:{service}:{principal_scope}:"
        f"{idem_key}:{_RESPONSE_SUFFIX}"
    )


def _lock_key(service: str, principal_scope: str, idem_key: str) -> str:
    return (
        f"{_RESPONSE_KEY_PREFIX}:{service}:{principal_scope}:"
        f"{idem_key}:{_LOCK_SUFFIX}"
    )


def _owner_key(service: str, idem_key: str) -> str:
    return f"{_RESPONSE_KEY_PREFIX}:{service}:{idem_key}:{_OWNER_SUFFIX}"


async def get_key_owner(
    redis: aioredis.Redis,
    service: str,
    idem_key: str,
) -> IdempotencyKeyOwner | None:
    raw = await redis.get(_owner_key(service, idem_key))
    if raw is None:
        return None
    return IdempotencyKeyOwner.model_validate_json(raw)


async def set_key_owner(
    redis: aioredis.Redis,
    service: str,
    idem_key: str,
    owner: IdempotencyKeyOwner,
    ttl: int,
) -> None:
    await redis.setex(_owner_key(service, idem_key), ttl, owner.model_dump_json())


async def claim_key_owner(
    redis: aioredis.Redis,
    service: str,
    idem_key: str,
    owner: IdempotencyKeyOwner,
    ttl: int,
) -> ClaimKeyOwnerResult:
    result = await redis.set(
        _owner_key(service, idem_key),
        owner.model_dump_json(),
        nx=True,
        ex=ttl,
    )
    if result:
        return ClaimKeyOwnerResult.CREATED
    existing = await get_key_owner(redis, service, idem_key)
    if existing == owner:
        return ClaimKeyOwnerResult.EXISTING_COMPATIBLE
    return ClaimKeyOwnerResult.CONFLICT


async def get_cached_response(
    redis: aioredis.Redis,
    service: str,
    principal_scope: str,
    idem_key: str,
) -> CachedResponse | None:
    raw = await redis.get(_response_key(service, principal_scope, idem_key))
    if raw is None:
        return None
    return CachedResponse.model_validate_json(raw)


async def set_cached_response(
    redis: aioredis.Redis,
    service: str,
    principal_scope: str,
    idem_key: str,
    response: CachedResponse,
    ttl: int,
) -> None:
    await redis.setex(
        _response_key(service, principal_scope, idem_key),
        ttl,
        response.model_dump_json(),
    )


async def acquire_lock(
    redis: aioredis.Redis,
    service: str,
    principal_scope: str,
    idem_key: str,
    lock_ttl: int = 10,
) -> str | None:
    token = str(uuid.uuid4())
    result = await redis.set(
        _lock_key(service, principal_scope, idem_key),
        token,
        nx=True,
        ex=lock_ttl,
    )
    return token if result else None


_RELEASE_LOCK_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
end
return 0
"""

_RENEW_LOCK_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("pexpire", KEYS[1], ARGV[2])
end
return 0
"""


async def release_lock(
    redis: aioredis.Redis,
    service: str,
    principal_scope: str,
    idem_key: str,
    lock_token: str,
) -> None:
    """Release a lock only if the caller still owns it (atomic compare-delete).

    A token is mandatory: deleting without one could remove another request's
    lock and allow duplicate execution.
    """
    if lock_token is None:
        raise ValueError("lock_token is required to release a lock safely")
    key = _lock_key(service, principal_scope, idem_key)
    await redis.eval(_RELEASE_LOCK_LUA, 1, key, lock_token)


async def renew_lock(
    redis: aioredis.Redis,
    service: str,
    principal_scope: str,
    idem_key: str,
    lock_token: str,
    ttl_ms: int,
) -> bool:
    """Extend the lock TTL if the caller still owns it.

    Returns True when the lock was renewed, False when the token no longer
    owns the lock (e.g. another holder took over after an expiry window).
    """
    if lock_token is None:
        raise ValueError("lock_token is required to renew a lock")
    key = _lock_key(service, principal_scope, idem_key)
    result = await redis.eval(_RENEW_LOCK_LUA, 1, key, lock_token, ttl_ms)
    return bool(result)


async def wait_for_lock_and_get(
    redis: aioredis.Redis,
    service: str,
    principal_scope: str,
    idem_key: str,
    poll_interval: float = 0.1,
    max_wait: float = 10.0,
) -> CachedResponse | None:
    elapsed = 0.0
    while elapsed < max_wait:
        cached = await get_cached_response(redis, service, principal_scope, idem_key)
        if cached is not None:
            return cached
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
    return None
