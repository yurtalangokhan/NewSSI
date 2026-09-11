"""Tests for ThreadRepository run_kind discriminator and querying.

Spec: .tmp/flow-canvas-design.md section 6.1, 9.1.
Brief: .tmp/flow-canvas-task-40-brief.md
"""

from __future__ import annotations

import importlib.util
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from core.db.models.thread import ThreadModel
from core.db.repositories.thread_repo import ThreadRepository


class _Result:
    def __init__(
        self, row: ThreadModel | None = None, rows: list[ThreadModel] | None = None
    ) -> None:
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
    run_kind: str = "production",
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> ThreadModel:
    now = datetime(2026, 8, 14, 12, tzinfo=UTC)
    return ThreadModel(
        thread_id=thread_id or uuid4(),
        run_kind=run_kind,
        metadata_={"user_id": "user-1"},
        status="idle",
        created_at=created_at or now,
        updated_at=updated_at or now,
        last_message_at=now,
        last_accessed_at=now,
    )


def _repository_with_session(session: _Session) -> ThreadRepository:
    repository = ThreadRepository()

    @asynccontextmanager
    async def fake_session():
        yield session

    repository._session = fake_session  # type: ignore[method-assign]
    return repository


@pytest.mark.asyncio
async def test_thread_defaults_to_production_run_kind():
    """40.1 — add_thread defaults to production run_kind when omitted."""
    row = _thread(run_kind="production")
    session = _Session([_Result(row=row)])
    repo = _repository_with_session(session)

    saved = await repo.add_thread({"thread_id": str(row.thread_id)})
    assert saved is not None
    assert saved["run_kind"] == "production"

    stmt = session.execute.call_args[0][0]
    compiled = str(stmt.compile(dialect=postgresql.dialect()))
    assert "run_kind" in compiled


@pytest.mark.asyncio
async def test_thread_accepts_explicit_playground_run_kind():
    """40.2 — add_thread persists explicit playground run_kind."""
    row = _thread(run_kind="playground")
    session = _Session([_Result(row=row)])
    repo = _repository_with_session(session)

    saved = await repo.add_thread({"thread_id": str(row.thread_id), "run_kind": "playground"})
    assert saved is not None
    assert saved["run_kind"] == "playground"


@pytest.mark.asyncio
async def test_list_threads_filters_by_run_kinds():
    """40.3 — list_threads applies run_kinds IN filter when provided."""
    session = _Session([_Result(rows=[_thread(run_kind="production")])])
    repo = _repository_with_session(session)

    # Filter with run_kinds
    await repo.list_threads(run_kinds=["production"])
    stmt = session.execute.call_args[0][0]
    compiled = str(stmt.compile(dialect=postgresql.dialect()))
    assert "thread.run_kind IN" in compiled

    # No filter
    session2 = _Session([_Result(rows=[_thread()])])
    repo2 = _repository_with_session(session2)
    await repo2.list_threads(run_kinds=None)
    stmt2 = session2.execute.call_args[0][0]
    compiled2 = str(stmt2.compile(dialect=postgresql.dialect()))
    assert "thread.run_kind IN" not in compiled2


@pytest.mark.asyncio
async def test_list_chat_sessions_filters_by_run_kinds():
    """40.4 — list_chat_sessions_by_activity applies run_kinds filter."""
    session = _Session([_Result(rows=[_thread(run_kind="production")])])
    repo = _repository_with_session(session)

    await repo.list_chat_sessions_by_activity(run_kinds=["production"])
    stmt = session.execute.call_args[0][0]
    compiled = str(stmt.compile(dialect=postgresql.dialect()))
    assert "thread.run_kind IN" in compiled


def test_migration_0040_structure_and_types(monkeypatch: pytest.MonkeyPatch) -> None:
    """40.5 & 40.6 — the run_kind migration structure, upgrade, downgrade, and server_default."""
    migration_path = (
        Path(__file__).resolve().parents[3]
        / "src"
        / "core"
        / "db"
        / "migrations"
        / "versions"
        / "0040_add_thread_run_kind.py"
    )
    spec = importlib.util.spec_from_file_location("m0040", migration_path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.revision == "0040"
    assert migration.down_revision == "0039"

    added_columns = []
    executed_sql = []

    class _Inspector:
        def get_columns(self, table_name: str) -> list[dict[str, str]]:
            return [{"name": "thread_id"}]

    def add_column(table_name: str, column: sa.Column[object]) -> None:
        added_columns.append(column)

    def execute(sql: str) -> None:
        executed_sql.append(sql)

    monkeypatch.setattr(migration.op, "get_bind", lambda: object())
    monkeypatch.setattr(sa, "inspect", lambda _b: _Inspector())
    monkeypatch.setattr(migration.op, "add_column", add_column)
    monkeypatch.setattr(migration.op, "execute", execute)

    migration.upgrade()
    assert len(added_columns) == 1
    assert added_columns[0].name == "run_kind"
    assert added_columns[0].server_default.arg == "production"

    migration.downgrade()
    assert any("DROP INDEX IF EXISTS ix_thread_run_kind" in s for s in executed_sql)
    assert any("ALTER TABLE thread DROP COLUMN IF EXISTS run_kind" in s for s in executed_sql)


def test_alembic_history_has_one_head():
    """40.7 — alembic migration history has exactly one head."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    migrations_dir = Path(__file__).resolve().parents[3] / "src" / "core" / "db" / "migrations"
    config = Config()
    config.set_main_option("script_location", str(migrations_dir))
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    assert heads == ["0045"]
