# Copyright (c) 2026 Agentic AI Platform
"""Translate storage driver failures at the database boundary."""

from collections.abc import Iterator
from contextlib import contextmanager

from error_contract import (
    CollectionNotFoundError,
    DatabaseConnectionError,
    DatabaseOperationError,
    DatabaseTimeoutError,
)
from neo4j.exceptions import DriverError, Neo4jError, ServiceUnavailable, SessionExpired
from pymilvus.exceptions import (
    CollectionNotExistException,
    ConnectError,
    MilvusException,
    MilvusUnavailableException,
)
from sqlalchemy.exc import DBAPIError, SQLAlchemyError, TimeoutError as SQLAlchemyTimeoutError


@contextmanager
def database_errors() -> Iterator[None]:
    """Keep driver diagnostics in the exception chain, outside public messages."""
    try:
        yield
    except (TimeoutError, SQLAlchemyTimeoutError) as exc:
        raise DatabaseTimeoutError from exc
    except (
        OSError,
        ServiceUnavailable,
        SessionExpired,
        ConnectError,
        MilvusUnavailableException,
    ) as exc:
        raise DatabaseConnectionError from exc
    except CollectionNotExistException as exc:
        raise CollectionNotFoundError from exc
    except DBAPIError as exc:
        sqlstate = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", "")
        if exc.connection_invalidated or str(sqlstate).startswith("08"):
            raise DatabaseConnectionError from exc
        raise DatabaseOperationError from exc
    except (SQLAlchemyError, MilvusException, DriverError, Neo4jError) as exc:
        raise DatabaseOperationError from exc
