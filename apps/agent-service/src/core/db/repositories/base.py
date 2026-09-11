"""Base repository with shared async session helpers."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from core.db.engine import get_session_factory
from core.logger import get_logger

logger = get_logger(__name__)


class BaseRepository:
    """Provides a scoped async session via ``_session()``.

    Every concrete repository inherits from this class and uses
    ``async with self._session() as session:`` for database access.
    The session is committed on success and rolled back on exception.
    """

    @asynccontextmanager
    async def _session(self) -> AsyncGenerator[AsyncSession, None]:
        """Yield a transactional ``AsyncSession``.

        Commits on success, rolls back on exception.
        """
        factory = get_session_factory()
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
