import redis.asyncio as aioredis

from idempotency.config import IdempotencyConfig


class AsyncRedisPool:
    _pool: aioredis.Redis | None = None

    @classmethod
    async def connect(cls, config: IdempotencyConfig) -> aioredis.Redis:
        if cls._pool is None:
            cls._pool = aioredis.Redis(
                host=config.redis_host,
                port=config.redis_port,
                db=config.redis_db,
                password=config.redis_password or None,
                decode_responses=True,
            )
        return cls._pool

    @classmethod
    async def close(cls) -> None:
        if cls._pool:
            await cls._pool.aclose()
            cls._pool = None
