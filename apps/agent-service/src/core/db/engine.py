"""SQLAlchemy async engine and session factory.

Exposes a singleton *AsyncEngine* and *async_sessionmaker* used by the
repository layer.  The engine is created lazily on first call to
:func:`get_db_engine`.

This module sits **alongside** the existing ``psycopg_pool`` connections
used by LangGraph (checkpointer / langgraph-store).  It does NOT replace
them — those pools are managed by LangGraph's own async savers and must
keep their ``autocommit=True`` / ``dict_row`` settings.

The SQLAlchemy engine here is for the **application's own tables**
(assistant, thread, sync_schedules, datasource_airbyte_mapping, etc.).
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.settings import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


# ---------------------------------------------------------------------------
# URL builder
# ---------------------------------------------------------------------------

def _build_url(*, driver: str = "asyncpg") -> str:
    """Build a PostgreSQL DSN from environment config.

    Parameters
    ----------
    driver:
        SQLAlchemy dialect+driver name.  Defaults to ``asyncpg`` for
        the async engine; ``psycopg`` can be passed for Alembic (sync).
    """
    if settings.POSTGRES_PASSWORD is None:
        raise ValueError("POSTGRES_PASSWORD is not set")
    return (
        f"postgresql+{driver}://{settings.POSTGRES_USER}:"
        f"{settings.POSTGRES_PASSWORD.get_secret_value()}@"
        f"{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/"
        f"{settings.POSTGRES_DB}"
    )


# ---------------------------------------------------------------------------
# Engine & session factory
# ---------------------------------------------------------------------------

def get_db_engine() -> AsyncEngine:
    """Return the singleton ``AsyncEngine``, creating it on first call."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            _build_url(),
            pool_size=settings.POSTGRES_MIN_CONNECTIONS_PER_POOL,
            max_overflow=settings.POSTGRES_MAX_CONNECTIONS_PER_POOL,
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


# ---------------------------------------------------------------------------
# Teardown
# ---------------------------------------------------------------------------

async def close_db_engine() -> None:
    """Dispose the engine and reset module-level singletons."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        logger.info("SQLAlchemy async engine disposed.")
        _engine = None
        _session_factory = None
