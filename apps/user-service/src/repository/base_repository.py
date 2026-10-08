from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from error_contract import DatabaseConnectionError, DatabaseOperationError, DatabaseTimeoutError
from sqlalchemy.exc import DBAPIError, SQLAlchemyError, TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import engine as db_engine


class BaseRepository:
    @asynccontextmanager
    async def _session(self) -> AsyncGenerator[AsyncSession, None]:
        scope = db_engine.get_current_scope()
        if scope is not None:
            # Request-scoped: opened lazily on first use, then shared with
            # every other repository call in this request. Commit/rollback
            # is owned by the middleware that published the scope --
            # committing here would break the atomicity that sharing the
            # session exists to provide.
            try:
                yield scope.get_or_open()
            except SQLAlchemyError as exc:
                raise _database_error(exc) from exc
            return

        factory = db_engine.get_session_factory()
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except SQLAlchemyError as exc:
                await session.rollback()
                raise _database_error(exc) from exc
            except Exception:
                # Roll back domain and control-flow failures, then preserve their identity.
                await session.rollback()
                raise


_CONNECTION_SQLSTATES = {"53300", "57P01", "57P02", "57P03"}


def _database_error(exc: SQLAlchemyError) -> Exception:
    if isinstance(exc, SQLAlchemyTimeoutError):
        return DatabaseTimeoutError()
    if isinstance(exc, DBAPIError):
        if exc.connection_invalidated or _is_connection_sqlstate(_sqlstate(exc.orig)):
            return DatabaseConnectionError()
        if _sqlstate(exc.orig) == "57014":
            return DatabaseTimeoutError()
    return DatabaseOperationError()


def _sqlstate(exc: BaseException) -> str | None:
    value = getattr(exc, "sqlstate", None) or getattr(exc, "pgcode", None)
    return str(value) if value else None


def _is_connection_sqlstate(sqlstate: str | None) -> bool:
    return bool(sqlstate and (sqlstate.startswith("08") or sqlstate in _CONNECTION_SQLSTATES))
