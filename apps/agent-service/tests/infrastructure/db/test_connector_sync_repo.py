"""``connector_sync_jobs``: one live job per datasource, decided by the database.

No database runs here. The statements are compiled for PostgreSQL and compared
with the index they rely on, which is declared three times: on the model, in
migration ``0052`` and as the arbiter of ``create_exclusive``.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
import uuid

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from core.exceptions import LiveSyncJobConflictError
from infrastructure.db.models.connector_sync import (
    ACTIVE_JOB_INDEX,
    ACTIVE_JOB_PREDICATE,
    ACTIVE_STATUSES,
    ConnectorSyncJobModel,
)
from infrastructure.db.repositories.connector_sync_repo import ConnectorSyncJobRepository

MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "src/infrastructure/db/migrations/versions/0052_one_live_sync_job_per_datasource.py"
)
JOB, DS = str(uuid.uuid4()), str(uuid.uuid4())


class _Result:
    def __init__(self, value: Any = None) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


class _Session:
    """Records what a repository method executes; optionally fails the statement.

    ``answers`` are what successive statements return from ``scalar_one_or_none``.
    """

    def __init__(self, error: Exception | None = None, answers: list[Any] | None = None) -> None:
        self.statements: list[Any] = []
        self._error = error
        self._answers = list(answers or [])

    async def execute(self, statement: Any) -> _Result:
        self.statements.append(statement)
        if self._error is not None:
            raise self._error
        return _Result(self._answers.pop(0) if self._answers else None)


def _repository(session: _Session) -> ConnectorSyncJobRepository:
    repository = ConnectorSyncJobRepository()

    @asynccontextmanager
    async def fake_session():
        yield session

    repository._session = fake_session  # type: ignore[method-assign]
    return repository


def _one_line(sql: str) -> str:
    return " ".join(sql.split())


def test_the_predicate_is_declared_once_and_the_model_uses_it():
    assert ACTIVE_STATUSES == ("pending", "running")
    assert ACTIVE_JOB_PREDICATE == "status IN ('pending', 'running')"

    index = next(index for index in ConnectorSyncJobModel.__table__.indexes if index.name == ACTIVE_JOB_INDEX)
    assert index.unique and [column.name for column in index.columns] == ["datasource_id"]
    assert str(index.dialect_options["postgresql"]["where"]) == ACTIVE_JOB_PREDICATE


def test_migration_0052_builds_the_index_the_model_declares():
    sql = _one_line(MIGRATION.read_text(encoding="utf-8"))

    assert (
        f"CREATE UNIQUE INDEX IF NOT EXISTS {ACTIVE_JOB_INDEX} "
        f"ON connector_sync_jobs (datasource_id) WHERE {ACTIVE_JOB_PREDICATE}"
    ) in sql
    assert f"DROP INDEX IF EXISTS {ACTIVE_JOB_INDEX}" in sql


@pytest.mark.asyncio
async def test_create_exclusive_lets_that_index_arbitrate():
    session = _Session()

    created = await _repository(session).create_exclusive(JOB, DS, status="pending", trigger="manual")

    assert created is None, "no row came back: the datasource already has a live job"
    [statement] = session.statements
    sql = _one_line(str(statement.compile(dialect=postgresql.dialect())))
    assert sql.startswith("INSERT INTO connector_sync_jobs")
    # PostgreSQL infers the arbiter index from the column and the predicate; a predicate
    # that differs from the index's is "no unique constraint matching", at run time.
    assert f"ON CONFLICT (datasource_id) WHERE {ACTIVE_JOB_PREDICATE} DO NOTHING RETURNING" in sql


def _violation(constraint: str) -> IntegrityError:
    detail = f'duplicate key value violates unique constraint "{constraint}"'
    return IntegrityError("UPDATE connector_sync_jobs SET status=$1 WHERE id = $2", ("running", JOB), Exception(detail))


@pytest.mark.asyncio
async def test_update_reports_a_second_live_job_as_a_conflict_not_as_sql():
    repository = _repository(_Session(_violation(ACTIVE_JOB_INDEX)))

    with pytest.raises(LiveSyncJobConflictError) as conflict:
        await repository.update(JOB, status="running")

    assert "UPDATE" not in str(conflict.value) and JOB in str(conflict.value)


@pytest.mark.asyncio
async def test_update_writes_a_live_status_only_over_a_live_row():
    # A worker declared dead by a sibling must not write RUNNING back over FAILED.
    session = _Session(answers=[None, "failed"])  # no row updated; the job exists, ended

    with pytest.raises(LiveSyncJobConflictError):
        await _repository(session).update(JOB, status="running", heartbeat_at=None)

    live_update, lookup = session.statements
    sql = _one_line(str(live_update.compile(dialect=postgresql.dialect())))
    assert "WHERE connector_sync_jobs.id = " in sql and "connector_sync_jobs.status IN (" in sql
    assert _one_line(str(lookup.compile(dialect=postgresql.dialect()))).startswith("SELECT connector_sync_jobs.status")

    # Unknown job: no row, no conflict. Terminal write: no status guard.
    assert await _repository(_Session(answers=[None, None])).update(JOB, status="running") is None
    session = _Session()
    assert await _repository(session).update(JOB, status="failed", error="x") is None
    [terminal_update] = session.statements
    assert "status IN (" not in _one_line(str(terminal_update.compile(dialect=postgresql.dialect())))


@pytest.mark.asyncio
async def test_update_leaves_other_integrity_errors_alone():
    repository = _repository(_Session(_violation("connector_sync_jobs_pkey")))

    with pytest.raises(IntegrityError):
        await repository.update(JOB, status="running")
