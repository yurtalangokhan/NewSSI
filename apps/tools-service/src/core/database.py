"""Database connection management."""

from inspect import isawaitable
from typing import Optional

try:
    import asyncpg
except ImportError:  # pragma: no cover - optional dependency in local dev
    asyncpg = None

from config_manager import env

from .observability import retry_async

#: What a failed health probe swallows: the driver's errors when it is installed
#: (``get_pool`` refuses to run without it), timeouts and socket errors.
_DB_ERRORS: tuple[type[BaseException], ...] = (
    (asyncpg.PostgresError, asyncpg.InterfaceError) if asyncpg is not None else ()
)
_HEALTH_ERRORS: tuple[type[BaseException], ...] = (*_DB_ERRORS, TimeoutError, OSError)


def _identifier(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


async def ensure_database_exists() -> None:
    """Create the tools-service role and database if they don't exist.

    With the admin credentials (``POSTGRES_ADMIN_USER`` / ``POSTGRES_ADMIN_PASSWORD``)
    this bootstraps like the other services' ``0000_bootstrap`` migrations: the login
    role is created, or its password set to the configured one, and the database is
    created owned by that role. Without them the service role itself has to exist and
    hold CREATEDB; the database is then created without an explicit owner.
    """
    if asyncpg is None:
        raise RuntimeError("asyncpg is not installed")

    config = env.tool_postgres_config
    admin_user, admin_password = env.POSTGRES_ADMIN_USER, env.POSTGRES_ADMIN_PASSWORD
    bootstrap = bool(admin_user and admin_password)
    conn = await asyncpg.connect(
        user=admin_user if bootstrap else config["user"],
        password=admin_password if bootstrap else config["password"],
        host=config["host"],
        port=config["port"],
        database="postgres",
        timeout=5,
    )
    try:
        if bootstrap:
            role_exists = await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", config["user"])
            await conn.execute(
                f"{'ALTER' if role_exists else 'CREATE'} ROLE {_identifier(config['user'])} "
                f"LOGIN PASSWORD {_literal(config['password'])}"
            )
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            config["database"],
        )
        if not exists:
            owner = f" OWNER {_identifier(config['user'])}" if bootstrap else ""
            await conn.execute(f"CREATE DATABASE {_identifier(config['database'])}{owner}")
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
        return env.tool_postgres_config

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
        except _HEALTH_ERRORS:
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
