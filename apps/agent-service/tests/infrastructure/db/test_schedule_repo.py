"""Tests for ScheduleRepository ensuring no cross-service RAG DB coupling."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4
import pytest
from datetime import datetime, timezone

from infrastructure.db.models.schedule import SyncScheduleModel
from infrastructure.db.repositories.schedule_repo import ScheduleRepository


class _Result:
    def __init__(self, rows: list[SyncScheduleModel] | None = None) -> None:
        self._rows = rows or []

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[SyncScheduleModel]:
        return self._rows


@pytest.mark.asyncio
async def test_schedule_repo_list_all_does_not_join_pg_collection():
    """list_all() must query SyncScheduleModel directly without cross-service DB joins."""
    import infrastructure.db.repositories.schedule_repo as mod

    # Verify PgCollection is not even in module namespace
    assert not hasattr(mod, "PgCollection")

    repo = ScheduleRepository()
    mock_session = AsyncMock()
    captured_stmt = []

    async def fake_execute(stmt):
        captured_stmt.append(stmt)
        item = SyncScheduleModel(
            id=uuid4(),
            datasource_id=uuid4(),
            cron_expression="0 0 * * *",
            last_run_status="success",
            enabled=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        return _Result([item])

    mock_session.execute = fake_execute

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_session():
        yield mock_session

    repo._read_session = fake_session

    schedules = await repo.list_all()
    assert len(schedules) == 1
    assert schedules[0]["last_run_status"] == "success"

    # Verify statement did not contain PgCollection join
    compiled_sql = str(captured_stmt[0])
    assert "langchain_pg_collection" not in compiled_sql.lower()
