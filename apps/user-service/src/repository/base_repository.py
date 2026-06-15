from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.engine import get_session_factory


class BaseRepository:
    @asynccontextmanager
    async def _session(self) -> AsyncGenerator[AsyncSession, None]:
        factory = get_session_factory()
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def _get_session(self) -> AsyncSession:
        factory = get_session_factory()
        return factory()
