"""Base repository with shared async session helpers."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import AsyncSession

from core.observability.logger import get_logger
from infrastructure.db.engine import get_session_factory
from infrastructure.db.error_mapping import database_errors

logger = get_logger(__name__)

#: Execution options that put a read on an AUTOCOMMIT connection.
_READ_EXECUTION_OPTIONS: dict[str, str] = {"isolation_level": "AUTOCOMMIT"}


class BaseRepository:
    """Provides scoped async sessions via ``_session()`` and ``_read_session()``.

    ``_session()`` is the write path: it commits on success and rolls back on
    exception. ``_read_session()`` is for SELECT-only work and issues no COMMIT.
    """

    @asynccontextmanager
    async def _session(self) -> AsyncGenerator[AsyncSession, None]:
        """Yield a transactional ``AsyncSession``.

        Commits on success, rolls back on exception.
        """
        with database_errors():
            factory = get_session_factory()
            async with factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

    @asynccontextmanager
    async def _read_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Yield a session for a read: no COMMIT, no BEGIN when the dialect allows.

        Every read used to go through ``_session()``, which means a SELECT was
        wrapped in BEGIN/COMMIT. That cost two extra round trips per read on top
        of the statement itself — with the reads a single chat turn issues, that
        is hundreds of avoidable round trips — and made a reader participate in
        the write path.

        An AUTOCOMMIT connection emits neither BEGIN nor COMMIT: a single
        statement is its own atomic snapshot in PostgreSQL, which is exactly
        what a read needs. Connections are returned to the pool with the
        isolation level reset by SQLAlchemy's ``IsolationLevelCharacteristic``,
        so no later writer inherits it.

        Only for statements that do not mutate. A write on this session would
        run outside a transaction, and a multi-statement read would lose its
        shared snapshot — both are asserted against in
        ``tests/core/test_repository_read_session.py``.
        """
        with database_errors():
            factory = get_session_factory()
            async with factory() as session:
                await _use_autocommit_for_reads(session)
                yield session


async def _use_autocommit_for_reads(session: AsyncSession) -> None:
    """Apply the read execution options, tolerating a dialect without AUTOCOMMIT.

    asyncpg supports AUTOCOMMIT and that is what this service runs on; a
    different driver that does not would fail loudly at every read, so a
    dialect that rejects the option degrades to a plain (still non-committing)
    session instead.
    """
    try:
        await session.connection(execution_options=dict(_READ_EXECUTION_OPTIONS))
    except (ArgumentError, NotImplementedError) as exc:
        logger.debug("Dialect rejected AUTOCOMMIT reads (%s); using a plain session.", exc)
