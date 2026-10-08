"""Normalize driver failures while preserving domain-owned constraint handling."""

from collections.abc import Iterator
from contextlib import contextmanager

from error_contract import DatabaseConnectionError, DatabaseOperationError, DatabaseTimeoutError
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError, TimeoutError as SQLAlchemyTimeoutError


@contextmanager
def database_errors() -> Iterator[None]:
    try:
        yield
    except IntegrityError:
        # Repositories own constraint-specific conflict decisions.
        raise
    except (TimeoutError, SQLAlchemyTimeoutError) as exc:
        raise DatabaseTimeoutError() from exc
    except OSError as exc:
        raise DatabaseConnectionError() from exc
    except DBAPIError as exc:
        sqlstate = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", "")
        if exc.connection_invalidated or str(sqlstate).startswith("08"):
            raise DatabaseConnectionError() from exc
        raise DatabaseOperationError() from exc
    except SQLAlchemyError as exc:
        raise DatabaseOperationError() from exc
