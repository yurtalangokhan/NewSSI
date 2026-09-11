"""Database connection management."""

from inspect import isawaitable
from typing import Optional

try:
    import asyncpg
except ImportError:  # pragma: no cover - optional dependency in local dev
    asyncpg = None

from .observability import retry_async
from .settings import get_settings


async def ensure_database_exists() -> None:
    """Create the configured tools-service database if it doesn't exist."""
    if asyncpg is None:
        raise RuntimeError("asyncpg is not installed")

    config = get_settings().postgres_config
    conn = await asyncpg.connect(
        user=config["user"],
        password=config["password"],
        host=config["host"],
        port=config["port"],
        database="postgres",
        timeout=5,
    )
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            config["database"],
        )
        if not exists:
            await conn.execute(f'CREATE DATABASE "{config["database"]}"')
    finally:
        await conn.close()


class DatabaseManager:
    """
    Singleton manager for database connection pool.

    Provides async connection pooling with automatic lifecycle management.
    Uses environment variables for configuration.
    """

    _instance: Optional["DatabaseManager"] = None
    _pool: object | None = None

    def __new__(cls) -> "DatabaseManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def config(self) -> dict:
        """Get database configuration from centralized settings."""
        return get_settings().postgres_config

    async def get_pool(self):
        """
        Get or create the database connection pool.

        Returns:
            asyncpg.Pool: The database connection pool.
        """
        if asyncpg is None:
            raise RuntimeError("asyncpg is not installed")

        if self._pool is None:

            async def ensure_database_operation() -> None:
                ensure_result = ensure_database_exists()
                if isawaitable(ensure_result):
                    await ensure_result

            await retry_async(
                ensure_database_operation,
                operation_name="ensure_database",
                dependency="postgres",
            )
            config = self.config
            self._pool = await retry_async(
                lambda: asyncpg.create_pool(
                    user=config["user"],
                    password=config["password"],
                    host=config["host"],
                    port=config["port"],
                    database=config["database"],
                    min_size=2,
                    max_size=10,
                ),
                operation_name="create_pool",
                dependency="postgres",
            )
        return self._pool

    async def close(self) -> None:
        """Close the database connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def health_check(self) -> bool:
        """
        Check if database connection is healthy.

        Returns:
            bool: True if connection is healthy, False otherwise.
        """
        try:
            pool = await self.get_pool()
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception:
            return False


# Global instance for convenience
db_manager = DatabaseManager()


async def get_db_pool():
    """
    Convenience function to get the database pool.

    Returns:
        asyncpg.Pool: The database connection pool.
    """
    return await db_manager.get_pool()


async def close_db_pool() -> None:
    """Convenience function to close the database pool."""
    await db_manager.close()
