"""SQLAlchemy async engine and session factory.

Exposes a singleton *AsyncEngine* and *async_sessionmaker* used by the
repository layer.  The engine is created lazily on first call to
:func:`get_db_engine`.
"""

from __future__ import annotations

from config_manager import env
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.shared.observability import get_logger

logger = get_logger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _build_url(*, driver: str = "asyncpg") -> str:
    """Build a PostgreSQL DSN from environment config using SQLAlchemy URL.create.

    Parameters
    ----------
    driver:
        SQLAlchemy dialect driver name (default ``asyncpg``).
    """
    return URL.create(
        drivername=f"postgresql+{driver}",
        username=env.POSTGRES_RAG_SERVICE_USER,
        password=env.POSTGRES_RAG_SERVICE_PASSWORD,
        host=env.POSTGRES_HOST,
        port=env.POSTGRES_PORT,
        database=env.POSTGRES_RAG_SERVICE_DB,
    ).render_as_string(hide_password=False)


def get_db_engine() -> AsyncEngine:
    """Return the singleton ``AsyncEngine``, creating it on first call."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            _build_url(),
            pool_size=10,
            max_overflow=20,
            echo=False,
        )
        logger.info("SQLAlchemy async engine created.")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the singleton session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_db_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_async_session() -> AsyncSession:
    """Convenience: create a new ``AsyncSession`` from the factory."""
    factory = get_session_factory()
    return factory()


async def close_db_engine() -> None:
    """Dispose the engine and reset module-level singletons."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        logger.info("SQLAlchemy async engine disposed.")
        _engine = None
        _session_factory = None
