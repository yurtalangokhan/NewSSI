"""Base repository with shared session helpers."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.errors import database_errors
from src.shared.observability import get_logger
from src.shared.postgres.engine import get_session_factory

logger = get_logger(__name__)


class BaseRepository:
    """Provides a scoped async session via ``_session()``."""

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
                except Exception:  # Roll back before translating the failure.
                    await session.rollback()
                    raise
