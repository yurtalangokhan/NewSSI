"""ThreadRepository can filter by "any of several owner ids" server-side.

chat_service._list_user_threads fetches up to 1000 rows and filters them
in Python when a caller has more than one owner id (legacy identities
migrated to a new one). The single-value `metadata_filter` only expresses a
JSONB containment match against one exact value, so there was no way to ask
Postgres for "user_id is any of these" directly -- this adds that, as an
OR of containment checks, so the Python-side over-fetch-and-filter step can
be replaced by a real WHERE clause.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from core.types.session_names import DEFAULT_SESSION_NAME
from infrastructure.db.models.thread import ThreadModel
from infrastructure.db.repositories.thread_repo import ThreadRepository


class _Result:
    def __init__(self, rows: list[ThreadModel] | None = None) -> None:
        self._rows = rows or []

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[ThreadModel]:
        return self._rows


class _Session:
    def __init__(self, results: list[_Result]) -> None:
        self.execute = AsyncMock(side_effect=results)


def _thread(user_id: str) -> ThreadModel:
    now = datetime(2026, 9, 16, 12, tzinfo=UTC)
    return ThreadModel(
        thread_id=uuid4(),
        run_kind="production",
        metadata_={"user_id": user_id},
        status="idle",
        created_at=now,
        updated_at=now,
        last_message_at=now,
        last_accessed_at=now,
    )


def _repository_with_session(session: _Session) -> ThreadRepository:
    repository = ThreadRepository()

    @asynccontextmanager
    async def fake_session():
        yield session

    # Reads go through ``_read_session`` and writes through ``_session``; the
    # helper injects the same fake into both so a test does not depend on
    # which one the method under test happens to use.
    repository._session = fake_session  # type: ignore[method-assign]
    repository._read_session = fake_session  # type: ignore[method-assign]
    return repository


@pytest.mark.asyncio
async def test_list_threads_ors_together_a_containment_check_per_candidate():
    session = _Session([_Result(rows=[_thread("user-1"), _thread("legacy-user-1")])])
    repo = _repository_with_session(session)

    result = await repo.list_threads(
        metadata_filter_any=[{"user_id": "user-1"}, {"user_id": "legacy-user-1"}]
    )

    assert len(result) == 2
    stmt = session.execute.call_args[0][0]
    compiled = str(stmt.compile(dialect=postgresql.dialect()))
    assert compiled.count("@>") == 2
    assert " OR " in compiled


@pytest.mark.asyncio
async def test_list_threads_with_a_single_candidate_still_filters():
    session = _Session([_Result(rows=[_thread("user-1")])])
    repo = _repository_with_session(session)

    await repo.list_threads(metadata_filter_any=[{"user_id": "user-1"}])

    stmt = session.execute.call_args[0][0]
    compiled = str(stmt.compile(dialect=postgresql.dialect()))
    assert compiled.count("@>") == 1


@pytest.mark.asyncio
async def test_list_threads_with_no_candidates_applies_no_metadata_filter():
    session = _Session([_Result(rows=[_thread("user-1")])])
    repo = _repository_with_session(session)

    await repo.list_threads(metadata_filter_any=[])

    stmt = session.execute.call_args[0][0]
    compiled = str(stmt.compile(dialect=postgresql.dialect()))
    assert "@>" not in compiled


@pytest.mark.asyncio
async def test_list_chat_sessions_by_activity_ors_together_candidates():
    session = _Session([_Result(rows=[_thread("user-1"), _thread("legacy-user-1")])])
    repo = _repository_with_session(session)

    result = await repo.list_chat_sessions_by_activity(
        metadata_filter_any=[{"user_id": "user-1"}, {"user_id": "legacy-user-1"}]
    )

    assert len(result) == 2
    stmt = session.execute.call_args[0][0]
    compiled = str(stmt.compile(dialect=postgresql.dialect()))
    assert compiled.count("@>") == 2
    assert " OR " in compiled


@pytest.mark.asyncio
async def test_list_chat_sessions_by_activity_filters_name_case_insensitively_and_escapes_wildcards():
    session = _Session([_Result(rows=[])])
    repo = _repository_with_session(session)

    await repo.list_chat_sessions_by_activity(name_contains="100%_off")

    compiled = session.execute.call_args[0][0].compile(dialect=postgresql.dialect())
    assert "ILIKE" in str(compiled).upper()
    assert "ESCAPE" in str(compiled).upper()
    assert "%100\\%\\_off%" in compiled.params.values()


@pytest.mark.asyncio
async def test_list_chat_sessions_by_activity_escapes_backslash_in_name_filter():
    session = _Session([_Result(rows=[])])
    repo = _repository_with_session(session)

    await repo.list_chat_sessions_by_activity(name_contains="a\\b")

    compiled = session.execute.call_args[0][0].compile(dialect=postgresql.dialect())
    assert "ESCAPE" in str(compiled).upper()
    assert "%a\\\\b%" in compiled.params.values()


@pytest.mark.asyncio
async def test_list_chat_sessions_by_activity_trims_padded_name_filter():
    session = _Session([_Result(rows=[])])
    repo = _repository_with_session(session)

    await repo.list_chat_sessions_by_activity(name_contains="  Report ")

    compiled = session.execute.call_args[0][0].compile(dialect=postgresql.dialect())
    assert "%Report%" in compiled.params.values()


@pytest.mark.asyncio
async def test_list_chat_sessions_by_activity_name_filter_skips_placeholder_named_sessions():
    session = _Session([_Result(rows=[])])
    repo = _repository_with_session(session)

    await repo.list_chat_sessions_by_activity(name_contains="chat")

    compiled = session.execute.call_args[0][0].compile(dialect=postgresql.dialect())
    assert DEFAULT_SESSION_NAME in compiled.params.values()
    assert "!=" in str(compiled)


@pytest.mark.asyncio
async def test_list_chat_sessions_by_activity_ignores_blank_name_filter():
    session = _Session([_Result(rows=[])])
    repo = _repository_with_session(session)

    await repo.list_chat_sessions_by_activity(name_contains="   ")

    compiled = str(session.execute.call_args[0][0].compile(dialect=postgresql.dialect()))
    assert "ILIKE" not in compiled.upper()


@pytest.mark.asyncio
async def test_list_chat_sessions_by_activity_agent_only_requires_a_nonzero_persona():
    session = _Session([_Result(rows=[])])
    repo = _repository_with_session(session)

    await repo.list_chat_sessions_by_activity(agents_only=True)

    compiled = session.execute.call_args[0][0].compile(dialect=postgresql.dialect())
    assert "persona_id" in compiled.params.values()
    assert "IS NOT NULL" in str(compiled).upper()
    assert "NOT IN" in str(compiled).upper()
