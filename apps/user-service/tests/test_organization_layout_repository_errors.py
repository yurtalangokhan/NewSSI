"""Failure translation tests for shared organization layout persistence."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from sqlalchemy.exc import IntegrityError

from src.core.exceptions import ConflictError, NotFoundError
from src.repository.organization_layout_repository import OrganizationLayoutRepository


class DatabaseError:
    """Small database-driver error stand-in with a SQLSTATE value."""

    def __init__(self, sqlstate: str) -> None:
        self.sqlstate = sqlstate


class FailingSession:
    """Session that raises a persistence error at the repository boundary."""

    def __init__(self, sqlstate: str) -> None:
        self.sqlstate = sqlstate

    async def execute(self, _statement: object) -> None:
        raise IntegrityError("statement", {}, DatabaseError(self.sqlstate))


class ErrorRepository(OrganizationLayoutRepository):
    """Repository using the real bulk-upsert logic with a failing session."""

    def __init__(self, sqlstate: str) -> None:
        self.sqlstate = sqlstate

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[FailingSession]:
        yield FailingSession(self.sqlstate)


@pytest.mark.asyncio
async def test_bulk_upsert_translates_non_foreign_key_integrity_failure_to_conflict() -> None:
    """A persistence conflict isn't misreported as a deleted organization."""
    repository = ErrorRepository("23505")

    with pytest.raises(ConflictError):
        await repository.bulk_upsert_positions(
            [{"organization_id": uuid.uuid4(), "x": 1.0, "y": 2.0}]
        )


@pytest.mark.asyncio
async def test_bulk_upsert_translates_foreign_key_integrity_failure_to_not_found() -> None:
    """A concurrent organization deletion remains a not-found response."""
    repository = ErrorRepository("23503")

    with pytest.raises(NotFoundError):
        await repository.bulk_upsert_positions(
            [{"organization_id": uuid.uuid4(), "x": 1.0, "y": 2.0}]
        )
