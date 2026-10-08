"""Spec: stored facts must not accumulate without bound. Before this,
only list_for_recall capped how many facts were *read* (LIMIT MAX_FACTS);
nothing capped how many were *stored*, so a long-lived, chatty user's
user_memory rows grew forever and old, possibly stale or contradictory
facts lingered in the table indefinitely.

delete_oldest_excess(user_id, keep) deletes every row for that user beyond
the `keep` most recently created ones, verified here by compiling the real
DELETE statement and running it against an actual (in-memory) SQLite table
-- not just asserting session.execute was called.
"""

import sqlite3
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import sqlite

from src.repository.user_memory_repository import UserMemoryRepository


def _repository_with_session(session: MagicMock) -> UserMemoryRepository:
    repository = UserMemoryRepository()

    @asynccontextmanager
    async def session_context():
        yield session

    repository._session = session_context  # type: ignore[method-assign]
    return repository


def _seed_table(db: sqlite3.Connection, user_id: uuid.UUID, rows: list[tuple[str, str, str]]) -> None:
    # postgresql.UUID(as_uuid=True)'s generic (non-Postgres-dialect) literal
    # bind processor renders a UUID as its dashless .hex form, not str(uuid)
    # -- match that here so the compiled WHERE clause actually matches rows.
    db.execute(
        "CREATE TABLE user_memory ("
        "id TEXT, user_id TEXT, content TEXT, source TEXT, "
        "time_created TEXT, time_updated TEXT)"
    )
    db.executemany(
        "INSERT INTO user_memory VALUES (?, ?, ?, 'auto_extracted', ?, ?)",
        [(row_id, user_id.hex, content, created, created) for row_id, content, created in rows],
    )


@pytest.mark.asyncio
async def test_delete_oldest_excess_keeps_only_the_newest_rows():
    user_id = uuid.uuid4()
    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock(rowcount=0))
    repo = _repository_with_session(session)

    await repo.delete_oldest_excess(user_id, keep=2)

    stmt = session.execute.call_args.args[0]
    compiled = stmt.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True})

    with sqlite3.connect(":memory:") as db:
        _seed_table(
            db,
            user_id,
            [
                ("id-1", "oldest", "2024-01-01T00:00:00"),
                ("id-2", "middle", "2024-01-02T00:00:00"),
                ("id-3", "newest", "2024-01-03T00:00:00"),
            ],
        )
        db.execute(str(compiled))
        remaining = {
            row[0] for row in db.execute("SELECT content FROM user_memory").fetchall()
        }

    assert remaining == {"middle", "newest"}


@pytest.mark.asyncio
async def test_delete_oldest_excess_only_touches_the_given_user():
    user_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock(rowcount=0))
    repo = _repository_with_session(session)

    await repo.delete_oldest_excess(user_id, keep=0)

    stmt = session.execute.call_args.args[0]
    compiled = stmt.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True})

    with sqlite3.connect(":memory:") as db:
        _seed_table(db, user_id, [("id-1", "mine", "2024-01-01T00:00:00")])
        db.executemany(
            "INSERT INTO user_memory VALUES (?, ?, ?, 'auto_extracted', ?, ?)",
            [("id-2", other_user_id.hex, "theirs", "2024-01-01T00:00:00", "2024-01-01T00:00:00")],
        )
        db.execute(str(compiled))
        remaining = {row[0] for row in db.execute("SELECT content FROM user_memory").fetchall()}

    assert remaining == {"theirs"}


@pytest.mark.asyncio
async def test_delete_oldest_excess_returns_the_number_of_rows_deleted():
    user_id = uuid.uuid4()
    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock(rowcount=3))
    repo = _repository_with_session(session)

    deleted = await repo.delete_oldest_excess(user_id, keep=50)

    assert deleted == 3


@pytest.mark.asyncio
async def test_delete_oldest_excess_with_nothing_over_the_cap_deletes_nothing():
    user_id = uuid.uuid4()
    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock(rowcount=0))
    repo = _repository_with_session(session)

    await repo.delete_oldest_excess(user_id, keep=50)

    stmt = session.execute.call_args.args[0]
    compiled = stmt.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True})

    with sqlite3.connect(":memory:") as db:
        _seed_table(db, user_id, [("id-1", "only fact", "2024-01-01T00:00:00")])
        db.execute(str(compiled))
        remaining = {row[0] for row in db.execute("SELECT content FROM user_memory").fetchall()}

    assert remaining == {"only fact"}
