"""
Database connection management.
Provides a singleton DatabaseManager for async connection pooling.
"""

import os
from typing import Optional

try:
    import asyncpg
except ImportError:  # pragma: no cover - optional dependency in local dev
    asyncpg = None


class DatabaseManager:
    """
    Singleton manager for database connection pool.
    
    Provides async connection pooling with automatic lifecycle management.
    Uses environment variables for configuration.
    """
    
    _instance: Optional["DatabaseManager"] = None
    _pool: Optional[object] = None
    
    def __new__(cls) -> "DatabaseManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @property
    def config(self) -> dict:
        """Get database configuration from environment variables."""
        return {
            "user": os.environ.get("POSTGRES_USER", "postgres"),
            "password": os.environ.get("POSTGRES_PASSWORD", "your-super-secret-and-long-postgres-password"),
            "host": os.environ.get("POSTGRES_HOST", "db"),
            "port": int(os.environ.get("POSTGRES_PORT", 5432)),
            "database": os.environ.get("POSTGRES_DB", "postgres"),
        }
    
    async def get_pool(self):
        """
        Get or create the database connection pool.
        
        Returns:
            asyncpg.Pool: The database connection pool.
        """
        if asyncpg is None:
            raise RuntimeError("asyncpg is not installed")

        if self._pool is None:
            config = self.config
            self._pool = await asyncpg.create_pool(
                user=config["user"],
                password=config["password"],
                host=config["host"],
                port=config["port"],
                database=config["database"],
                min_size=2,
                max_size=10,
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
