"""SQLAlchemy async engine and session factory.

Exposes a singleton *AsyncEngine* and *async_sessionmaker* used by the
repository layer.  The engine is created lazily on first call to
:func:`get_db_engine`.

This module sits **alongside** the existing ``psycopg_pool`` connections
used by LangGraph (checkpointer / langgraph-store).  It does NOT replace
them — those pools are managed by LangGraph's own async savers and must
keep their ``autocommit=True`` / ``dict_row`` env.

The SQLAlchemy engine here is for the **application's own tables**
(assistant, thread, sync_schedules, datasource_connections, etc.).
"""

from __future__ import annotations

from typing import Any

from config_manager import env
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.observability.logger import get_logger

logger = get_logger(__name__)

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

    Uses :meth:`sqlalchemy.URL.create` rather than string interpolation so that
    reserved characters in the password (``@``, ``:``, ``/``, ``?``, ``#``) are
    percent-encoded instead of corrupting the DSN.

    Parameters
    ----------
    driver:
        SQLAlchemy dialect+driver name.  Defaults to ``asyncpg`` for
        the async engine; ``psycopg`` can be passed for Alembic (sync).
    """
    password = env.POSTGRES_AGENT_SERVICE_PASSWORD
    if password is None:
        raise ValueError("POSTGRES_AGENT_SERVICE_PASSWORD is not set")
    return URL.create(
        drivername=f"postgresql+{driver}",
        username=env.POSTGRES_AGENT_SERVICE_USER,
        password=password,
        host=env.POSTGRES_HOST,
        port=env.POSTGRES_PORT,
        database=env.POSTGRES_AGENT_SERVICE_DB,
    ).render_as_string(hide_password=False)


# ---------------------------------------------------------------------------
# Engine & session factory
# ---------------------------------------------------------------------------


def _validate_pool_config() -> None:
    """Reject pool settings that would fail obscurely at runtime.

    A zero/negative ``pool_size`` or ``max_overflow`` raises inside SQLAlchemy
    on first checkout, long after startup, and a non-positive timeout turns a
    saturated pool into an instant error instead of a queue.
    """
    if env.POSTGRES_POOL_SIZE < 1:
        raise ValueError(f"POSTGRES_POOL_SIZE ({env.POSTGRES_POOL_SIZE}) must be at least 1")
    if env.POSTGRES_MAX_OVERFLOW < 0:
        raise ValueError(f"POSTGRES_MAX_OVERFLOW ({env.POSTGRES_MAX_OVERFLOW}) must not be negative")
    if env.POSTGRES_POOL_TIMEOUT_SECONDS <= 0:
        raise ValueError(
            f"POSTGRES_POOL_TIMEOUT_SECONDS ({env.POSTGRES_POOL_TIMEOUT_SECONDS}) must be greater than zero"
        )
    if env.POSTGRES_COMMAND_TIMEOUT_SECONDS <= 0:
        raise ValueError(
            f"POSTGRES_COMMAND_TIMEOUT_SECONDS ({env.POSTGRES_COMMAND_TIMEOUT_SECONDS}) must be greater than zero"
        )


def _connect_args() -> dict[str, Any]:
    """asyncpg connect kwargs shared by every pooled connection.

    ``command_timeout`` bounds a single statement server-side, so a runaway
    query cannot hold a pooled connection forever. ``application_name`` shows up
    in ``pg_stat_activity``, which is what makes "who is holding these
    connections" answerable from the database side.
    """
    return {
        "command_timeout": env.POSTGRES_COMMAND_TIMEOUT_SECONDS,
        "server_settings": {"application_name": env.POSTGRES_APPLICATION_NAME},
    }


def get_db_engine() -> AsyncEngine:
    """Return the singleton ``AsyncEngine``, creating it on first call."""
    global _engine
    if _engine is None:
        _validate_pool_config()
        _engine = create_async_engine(
            _build_url(),
            pool_size=env.POSTGRES_POOL_SIZE,
            max_overflow=env.POSTGRES_MAX_OVERFLOW,
            pool_timeout=env.POSTGRES_POOL_TIMEOUT_SECONDS,
            pool_recycle=env.POSTGRES_POOL_RECYCLE_SECONDS,
            pool_use_lifo=env.POSTGRES_POOL_USE_LIFO,
            pool_pre_ping=True,
            connect_args=_connect_args(),
            echo=False,
        )
        logger.info(
            "SQLAlchemy async engine created.",
            extra={
                "event": "db.engine.created",
                "pool_size": env.POSTGRES_POOL_SIZE,
                "max_overflow": env.POSTGRES_MAX_OVERFLOW,
                "pool_timeout_seconds": env.POSTGRES_POOL_TIMEOUT_SECONDS,
                "pool_recycle_seconds": env.POSTGRES_POOL_RECYCLE_SECONDS,
                "pool_use_lifo": env.POSTGRES_POOL_USE_LIFO,
            },
        )
    return _engine


def get_pool_status() -> dict[str, Any]:
    """Current pool occupancy, or ``{}`` before the engine exists.

    Exposed so a saturation incident is diagnosable from the process instead of
    inferred from PostgreSQL's ``pg_stat_activity``. Never raises: a pool that
    cannot report its own state must not break the caller asking about it.
    """
    engine = _engine
    if engine is None:
        return {}
    try:
        pool = engine.pool
        return {
            "size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "summary": pool.status(),
        }
    except Exception as exc:
        logger.warning("Could not read DB pool status: %s", exc)
        return {}


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
