"""Without socket timeouts, a stalled Redis parks the request worker
forever -- every request holding the idempotency lock would block
indefinitely instead of failing fast. Spec TS-13.

These assertions read the kwargs actually handed to the Redis constructor.
Checking that a substring appears in the source proves nothing: `socket_timeout
= 0` means "no timeout" to redis-py, and a value that never reaches the
constructor would also satisfy a source-level check.
"""

from typing import Any

import pytest
import redis.asyncio as aioredis

from idempotency import AsyncRedisPool, IdempotencyConfig

_SOCKET_KWARGS = ("socket_connect_timeout", "socket_timeout")


@pytest.fixture
def captured_redis_kwargs(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Intercept the Redis constructor and return the kwargs it received."""
    captured: dict[str, Any] = {}

    class StubRedis:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

        async def aclose(self) -> None:
            captured["__closed__"] = True

    monkeypatch.setattr(aioredis, "Redis", StubRedis)
    # connect() memoises into a class attribute; clear it so the stub is used.
    monkeypatch.setattr(AsyncRedisPool, "_pool", None)
    return captured


async def _connect() -> dict[str, Any]:
    return await AsyncRedisPool.connect(
        IdempotencyConfig(
            redis_host="localhost",
            redis_port=6379,
            redis_db=0,
            redis_password="",
        )
    )


@pytest.mark.asyncio
async def test_client_sets_positive_socket_timeouts(
    captured_redis_kwargs: dict[str, Any],
) -> None:
    await _connect()

    for name in _SOCKET_KWARGS:
        assert name in captured_redis_kwargs, f"{name} never reached the Redis constructor"
        timeout = captured_redis_kwargs[name]
        assert timeout is not None, f"{name}=None disables the timeout entirely"
        assert isinstance(timeout, (int, float)) and timeout > 0, (
            f"{name}={timeout!r} would let a stalled Redis block forever; "
            "redis-py reads 0 or None as no timeout"
        )


@pytest.mark.asyncio
async def test_connect_is_memoised(captured_redis_kwargs: dict[str, Any]) -> None:
    """A second caller must reuse the pool, not open a second connection."""
    first = await _connect()
    second = await _connect()

    assert first is second


@pytest.mark.asyncio
async def test_close_resets_the_pool(captured_redis_kwargs: dict[str, Any]) -> None:
    await _connect()
    await AsyncRedisPool.close()
    assert AsyncRedisPool._pool is None

    # After close, a fresh connect must build a new client.
    await _connect()
    assert AsyncRedisPool._pool is not None
