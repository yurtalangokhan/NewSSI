"""Base repository with shared session helpers."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from langconnect.database.postgres.engine import get_session_factory

logger = logging.getLogger(__name__)


class BaseRepository:
    """Provides a scoped async session via ``_session()``."""

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
