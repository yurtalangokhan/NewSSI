"""Repository coverage for chat session activity timestamps."""

from __future__ import annotations

import asyncio
import importlib.util
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from core.db.models.thread import ThreadModel
from core.db.repositories.thread_repo import ThreadRepository


class _Result:
    def __init__(self, row: ThreadModel | None = None, rows: list[ThreadModel] | None = None) -> None:
        self._row = row
        self._rows = rows or []

    def scalar_one_or_none(self) -> ThreadModel | None:
        return self._row

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[ThreadModel]:
        return self._rows


class _Session:
    def __init__(self, results: list[_Result]) -> None:
        self._results = results
        self.execute = AsyncMock(side_effect=results)


def _thread(
    *,
    thread_id: UUID | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    last_message_at: datetime | None = None,
    last_accessed_at: datetime | None = None,
) -> ThreadModel:
    now = datetime(2026, 8, 7, 12, tzinfo=UTC)
    return ThreadModel(
        thread_id=thread_id or uuid4(),
        metadata_={"user_id": "user-1"},
        status="idle",
        created_at=created_at or now,
        updated_at=updated_at or now,
        last_message_at=last_message_at,
        last_accessed_at=last_accessed_at,
    )


def _repository_with_session(session: _Session) -> ThreadRepository:
    repository = ThreadRepository()

    @asynccontextmanager
    async def fake_session():
        yield session

    repository._session = fake_session  # type: ignore[method-assign]
    return repository


def _compiled_sql(statement: object) -> str:
    return str(
        statement.compile(  # type: ignore[union-attr]
            dialect=postgresql.dialect()
        )
    )


def _updated_column_names(statement: object) -> set[str]:
    return {column.key for column in statement._values}  # type: ignore[union-attr]


def test_thread_serialization_includes_activity_timestamps() -> None:
    last_message_at = datetime(2026, 8, 7, 11, tzinfo=UTC)
    last_accessed_at = datetime(2026, 8, 7, 12, tzinfo=UTC)

    serialized = ThreadRepository._to_dict(
        _thread(last_message_at=last_message_at, last_accessed_at=last_accessed_at)
    )

    assert serialized["last_message_at"] == last_message_at.isoformat()
    assert serialized["last_accessed_at"] == last_accessed_at.isoformat()


@pytest.mark.asyncio
async def test_mark_message_activity_updates_only_message_and_updated_timestamps() -> None:
    row = _thread()
    session = _Session([_Result(row=row)])
    repository = _repository_with_session(session)

    result = await repository.mark_message_activity(str(row.thread_id))

    statement = session.execute.await_args.args[0]
    sql = _compiled_sql(statement)
    assert result["thread_id"] == str(row.thread_id)
    assert _updated_column_names(statement) == {"last_message_at", "updated_at"}
    assert "UPDATE thread SET" in sql
    assert "RETURNING" in sql


@pytest.mark.asyncio
async def test_mark_accessed_updates_only_access_timestamp() -> None:
    row = _thread()
    session = _Session([_Result(row=row)])
    repository = _repository_with_session(session)

    result = await repository.mark_accessed(str(row.thread_id))

    statement = session.execute.await_args.args[0]
    sql = _compiled_sql(statement)
    assert result["thread_id"] == str(row.thread_id)
    assert _updated_column_names(statement) == {"last_accessed_at"}
    assert "UPDATE thread SET" in sql
    assert "RETURNING" in sql


@pytest.mark.asyncio
async def test_add_thread_preserves_omitted_activity_timestamps_on_conflict() -> None:
    last_message_at = datetime(2026, 8, 7, 10, tzinfo=UTC)
    last_accessed_at = datetime(2026, 8, 7, 11, tzinfo=UTC)
    row = _thread(last_message_at=last_message_at, last_accessed_at=last_accessed_at)
    session = _Session([_Result(row=row)])
    repository = _repository_with_session(session)

    result = await repository.add_thread(
        {
            "thread_id": str(row.thread_id),
            "metadata": {"user_id": "user-1", "title": "Renamed"},
            "status": "idle",
        }
    )

    sql = _compiled_sql(session.execute.await_args.args[0])
    conflict_update = sql.split("DO UPDATE SET", maxsplit=1)[1].split("RETURNING", maxsplit=1)[0]
    assert result["last_message_at"] == last_message_at.isoformat()
    assert result["last_accessed_at"] == last_accessed_at.isoformat()
    assert "last_message_at" not in conflict_update
    assert "last_accessed_at" not in conflict_update


@pytest.mark.asyncio
async def test_activity_updates_do_not_overwrite_each_other_when_called_concurrently() -> None:
    thread_id = uuid4()
    session = _Session([_Result(row=_thread(thread_id=thread_id)), _Result(row=_thread(thread_id=thread_id))])
    repository = _repository_with_session(session)

    await asyncio.gather(
        repository.mark_accessed(str(thread_id)),
        repository.mark_message_activity(str(thread_id)),
    )

    updated_columns = {
        frozenset(_updated_column_names(call.args[0])) for call in session.execute.await_args_list
    }
    assert updated_columns == {
        frozenset({"last_accessed_at"}),
        frozenset({"last_message_at", "updated_at"}),
    }


@pytest.mark.asyncio
async def test_activity_list_uses_keyset_order_without_changing_generic_list_order() -> None:
    before_activity = datetime(2026, 8, 7, 11, tzinfo=UTC)
    before_id = uuid4()
    session = _Session([_Result(rows=[])])
    repository = _repository_with_session(session)

    await repository.list_chat_sessions_by_activity(
        page_size=25,
        before_activity=before_activity.isoformat(),
        before_id=str(before_id),
        metadata_filter={"user_id": "user-1"},
    )

    sql = _compiled_sql(session.execute.await_args.args[0])
    assert "ORDER BY coalesce(thread.last_message_at, thread.created_at) DESC, thread.thread_id DESC" in sql
    assert "(coalesce(thread.last_message_at, thread.created_at), thread.thread_id) <" in sql
    assert "thread.metadata @> CAST" in sql
    assert session.execute.await_args.args[0]._limit_clause.value == 25

    generic_session = _Session([_Result(rows=[])])
    generic_repository = _repository_with_session(generic_session)
    await generic_repository.list_threads(limit=25)
    generic_sql = _compiled_sql(generic_session.execute.await_args.args[0])
    assert "ORDER BY thread.updated_at DESC" in generic_sql


@pytest.mark.asyncio
async def test_activity_list_next_page_retains_deterministic_order() -> None:
    base = datetime(2026, 8, 7, 12, tzinfo=UTC)
    first_page = [_thread(last_message_at=base), _thread(last_message_at=base - timedelta(minutes=1))]
    second_page = [
        _thread(last_message_at=base - timedelta(minutes=2)),
        _thread(last_message_at=base - timedelta(minutes=3)),
    ]
    session = _Session([_Result(rows=first_page), _Result(rows=second_page)])
    repository = _repository_with_session(session)

    first_result = await repository.list_chat_sessions_by_activity(page_size=2)
    second_result = await repository.list_chat_sessions_by_activity(
        page_size=2,
        before_activity=first_result[-1]["last_message_at"],
        before_id=first_result[-1]["thread_id"],
    )

    assert [item["thread_id"] for item in first_result + second_result] == [
        str(row.thread_id) for row in first_page + second_page
    ]
    second_sql = _compiled_sql(session.execute.await_args_list[1].args[0])
    assert "(coalesce(thread.last_message_at, thread.created_at), thread.thread_id) <" in second_sql


def test_activity_migration_adds_and_removes_timestamp_columns_and_index(monkeypatch: pytest.MonkeyPatch) -> None:
    migration_path = (
        Path(__file__).parents[2]
        / "src/core/db/migrations/versions/0027_add_thread_activity_timestamps.py"
    )
    spec = importlib.util.spec_from_file_location("thread_activity_migration", migration_path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    columns = {"thread_id", "created_at", "updated_at"}
    added_columns: list[sa.Column[object]] = []
    upgrade_execute: list[str] = []
    downgrade_execute: list[str] = []

    class _Inspector:
        def get_columns(self, _table_name: str) -> list[dict[str, str]]:
            return [{"name": name} for name in columns]

    def add_column(_table_name: str, column: sa.Column[object]) -> None:
        columns.add(column.name)
        added_columns.append(column)

    monkeypatch.setattr(migration.op, "get_bind", object)
    monkeypatch.setattr(sa, "inspect", lambda _bind: _Inspector())
    monkeypatch.setattr(migration.op, "add_column", add_column)
    monkeypatch.setattr(migration.op, "execute", upgrade_execute.append)
    migration.upgrade()
    monkeypatch.setattr(migration.op, "execute", downgrade_execute.append)
    migration.downgrade()

    upgrade_sql = "\n".join(upgrade_execute)
    downgrade_sql = "\n".join(downgrade_execute)
    assert migration.revision == "0027"
    assert migration.down_revision == "0026"
    assert [column.name for column in added_columns] == ["last_message_at", "last_accessed_at"]
    assert all(isinstance(column.type, sa.DateTime) for column in added_columns)
    assert "SET last_message_at = updated_at" in upgrade_sql
    assert "idx_thread_activity_order" in upgrade_sql
    assert "COALESCE(last_message_at, created_at)" in upgrade_sql
    assert "DROP INDEX IF EXISTS idx_thread_activity_order" in downgrade_sql
    assert "DROP COLUMN IF EXISTS last_message_at" in downgrade_sql
    assert "DROP COLUMN IF EXISTS last_accessed_at" in downgrade_sql


def test_activity_migration_does_not_backfill_unsent_sessions_on_second_upgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration_path = (
        Path(__file__).parents[2]
        / "src/core/db/migrations/versions/0027_add_thread_activity_timestamps.py"
    )
    spec = importlib.util.spec_from_file_location("thread_activity_migration", migration_path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    columns = {"thread_id", "created_at", "updated_at"}
    rows = [{"updated_at": "historical", "last_message_at": None}]
    executed_sql: list[str] = []

    class _Inspector:
        def get_columns(self, _table_name: str) -> list[dict[str, str]]:
            return [{"name": name} for name in columns]

    def add_column(_table_name: str, column: sa.Column[object]) -> None:
        columns.add(column.name)

    def execute(sql: str) -> None:
        executed_sql.append(sql)
        if sql.strip().startswith("UPDATE thread SET last_message_at"):
            for row in rows:
                if row["last_message_at"] is None:
                    row["last_message_at"] = row["updated_at"]

    bind = object()
    monkeypatch.setattr(migration.op, "get_bind", lambda: bind)
    monkeypatch.setattr(sa, "inspect", lambda _bind: _Inspector())
    monkeypatch.setattr(migration.op, "add_column", add_column)
    monkeypatch.setattr(migration.op, "execute", execute)

    migration.upgrade()
    rows.append({"updated_at": "new-unsent", "last_message_at": None})
    migration.upgrade()

    assert rows == [
        {"updated_at": "historical", "last_message_at": "historical"},
        {"updated_at": "new-unsent", "last_message_at": None},
    ]
    assert sum("UPDATE thread SET last_message_at" in sql for sql in executed_sql) == 1
