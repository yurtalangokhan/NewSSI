from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from contextvars import ContextVar

from config_manager import env
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_settings = env

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


class _RequestSessionScope:
    """Per-request holder for the shared session, created lazily.

    The session itself is opened on first use by a repository, not when the
    request starts: a request that never calls a repository (a health
    check, a pure auth/config lookup) should never open a real DB
    connection just because it happened to run inside the request-scoped
    middleware.
    """

    __slots__ = ("session",)

    def __init__(self) -> None:
        self.session: AsyncSession | None = None

    def get_or_open(self) -> AsyncSession:
        if self.session is None:
            factory = get_session_factory()
            self.session = factory()
        return self.session


# Spec T5: published by ``request_scoped_session`` for the lifetime of one
# HTTP request, so every ``BaseRepository`` instance constructed anywhere
# during that request shares the same session (and therefore the same
# transaction) instead of each repository call checking out its own
# connection. Unset (None) outside of a request -- startup code, scripts,
# and tests fall back to BaseRepository's own call-scoped session.
_current_scope: ContextVar["_RequestSessionScope | None"] = ContextVar("_current_scope", default=None)


def get_current_session() -> AsyncSession | None:
    """The session actually opened for the current request, if any.

    Returns ``None`` both outside of a request and inside one where no
    repository has opened the lazy session yet.
    """
    scope = _current_scope.get()
    return scope.session if scope is not None else None


def get_current_scope() -> "_RequestSessionScope | None":
    return _current_scope.get()


def get_db_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            _settings.database_url,
            # NullPool opened a new physical connection for every repository call.
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=1800,
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


@asynccontextmanager
async def request_scoped_session() -> AsyncGenerator[_RequestSessionScope, None]:
    """Publish a (lazily-populated) session scope for the duration of the
    block, and close whatever session actually got opened, if any.

    Pure plumbing: never commits or rolls back -- that decision depends on
    how the caller's work turned out (e.g. the HTTP response status), which
    this primitive has no visibility into. The caller owns that decision.
    """
    scope = _RequestSessionScope()
    token = _current_scope.set(scope)
    try:
        yield scope
    finally:
        _current_scope.reset(token)
        if scope.session is not None:
            await scope.session.close()


async def close_db_engine():
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
    # A factory built while _engine was patched out (e.g. a test faking
    # get_db_engine for a narrow purpose) never sets the real _engine
    # global, so it must be reset unconditionally -- otherwise it silently
    # outlives the test that created it and poisons every later one that
    # touches the database.
    _session_factory = None


def _build_url(driver: str = "asyncpg") -> str:
    return _settings.sync_database_url if driver == "psycopg" else _settings.database_url
