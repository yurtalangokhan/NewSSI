from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from config import get_settings

_settings = get_settings()

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_db_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            _settings.database_url,
            poolclass=NullPool,
            echo=False,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_db_engine(),
            expire_on_commit=False,
            autoflush=False,
            class_=AsyncSession,
        )
    return _session_factory


async def get_async_session() -> AsyncSession:
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def close_db_engine():
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


def _build_url(driver: str = "asyncpg") -> str:
    return _settings.sync_database_url
