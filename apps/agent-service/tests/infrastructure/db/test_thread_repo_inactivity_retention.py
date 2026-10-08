"""Spec: production-thread retention must key off inactivity, not creation
time. delete_threads_older_than (used for playground runs) filters on
created_at -- fine for short-lived throwaway runs, but wrong for real
conversations: a thread a user opened months ago and still chats in daily
would be deleted just for being old. delete_threads_inactive_since filters
on COALESCE(last_message_at, created_at) instead, matching the thread
table's own activity-ordering index expression.
"""

import sqlite3
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import sqlite

from infrastructure.db.repositories.thread_repo import ThreadRepository


def _repository_with_session(session) -> ThreadRepository:
    repo = ThreadRepository()

    @asynccontextmanager
    async def session_context():
        yield session

    repo._session = session_context  # type: ignore[method-assign]
    return repo


def _empty_select_result() -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    return result


@pytest.mark.asyncio
async def test_delete_threads_inactive_since_returns_deleted_ids():
    expired_id = str(uuid4())
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [expired_id]
    mock_res = MagicMock()
    mock_res.scalars.return_value = mock_scalars

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[mock_res, MagicMock()])
    repo = _repository_with_session(session)

    cutoff = datetime.now(UTC) - timedelta(days=90)
    deleted = await repo.delete_threads_inactive_since(run_kind="production", older_than=cutoff)

    assert deleted == [expired_id]
    assert session.execute.await_count == 2


@pytest.mark.asyncio
async def test_a_thread_with_recent_activity_survives_even_if_created_long_ago():
    # This is the exact scenario delete_threads_older_than gets wrong for
    # production threads: old creation date, but chatted in yesterday.
    session = MagicMock()
    session.execute = AsyncMock(return_value=_empty_select_result())
    repo = _repository_with_session(session)

    cutoff = datetime.now(UTC) - timedelta(days=90)
    await repo.delete_threads_inactive_since(run_kind="production", older_than=cutoff)

    stmt = session.execute.call_args_list[0].args[0]
    compiled = stmt.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True})

    with sqlite3.connect(":memory:") as db:
        db.execute(
            "CREATE TABLE thread (thread_id TEXT, run_kind TEXT, "
            "created_at TEXT, last_message_at TEXT)"
        )
        old_but_active = str(uuid4())
        old_and_abandoned = str(uuid4())
        db.executemany(
            "INSERT INTO thread VALUES (?, 'production', ?, ?)",
            [
                (old_but_active, "2020-01-01T00:00:00", _yesterday()),
                (old_and_abandoned, "2020-01-01T00:00:00", None),
            ],
        )
        # sqlite lacks COALESCE-with-NULL-comparison quirks other engines
        # have, but this still proves the predicate reads last_message_at
        # first and only falls back to created_at when it's NULL.
        matched = {
            row[0]
            for row in db.execute(f"SELECT thread_id FROM thread WHERE {predicate_of(compiled)}")
        }

    assert old_but_active not in matched
    assert old_and_abandoned in matched


def predicate_of(compiled) -> str:
    sql = str(compiled)
    return sql.split("WHERE", 1)[1]


def _yesterday() -> str:
    return (datetime.now(UTC) - timedelta(days=1)).isoformat()


@pytest.mark.asyncio
async def test_delete_threads_inactive_since_only_touches_the_given_run_kind():
    session = MagicMock()
    session.execute = AsyncMock(return_value=_empty_select_result())
    repo = _repository_with_session(session)

    cutoff = datetime.now(UTC) - timedelta(days=90)
    await repo.delete_threads_inactive_since(run_kind="production", older_than=cutoff)

    stmt = session.execute.call_args_list[0].args[0]
    compiled = stmt.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True})
    assert "run_kind" in str(compiled)
    assert "'production'" in str(compiled)
