"""KnowledgeEvidenceRepository: thread-scoped storage of retrieval evidence."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from schemas.knowledge_evidence import EvidenceKind, KnowledgeEvidence

from infrastructure.db.models.knowledge_evidence import KnowledgeEvidenceModel
from infrastructure.db.repositories.knowledge_evidence_repo import KnowledgeEvidenceRepository

THREAD_ID = UUID("7f7d8c1e-5e4b-4a57-9c1d-2f6f0d4b9a10")


def _evidence(query: str = "leave carry-over") -> KnowledgeEvidence:
    return KnowledgeEvidence(
        kind=EvidenceKind.DOCUMENT,
        tool="database_search",
        query=query,
        chunks=[{"ref": 1, "content": "Unused leave carries over."}],
        model_context="[1]\nUnused leave carries over.",
    )


class _Rows:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows


def _repo_with_session(session: Any) -> KnowledgeEvidenceRepository:
    repo = KnowledgeEvidenceRepository()

    @asynccontextmanager
    async def fake_session():
        yield session

    repo._session = fake_session  # type: ignore[method-assign]
    repo._read_session = fake_session  # type: ignore[method-assign]
    return repo


@pytest.mark.asyncio
async def test_add_persists_the_evidence_under_its_thread() -> None:
    session = MagicMock()
    session.flush = AsyncMock()
    repo = _repo_with_session(session)
    evidence = _evidence()

    evidence_id = await repo.add(THREAD_ID, evidence)

    model: KnowledgeEvidenceModel = session.add.call_args.args[0]
    assert model.id == evidence_id
    assert model.thread_id == THREAD_ID
    assert model.kind == "document"
    assert model.tool == "database_search"
    assert model.schema_version == 1
    assert model.payload == evidence.model_dump(mode="json")
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_many_is_scoped_to_the_thread_and_requested_ids() -> None:
    wanted, other = uuid4(), uuid4()
    session = MagicMock()
    statements: list[Any] = []

    async def execute(statement):
        statements.append(statement)
        return _Rows([(wanted, _evidence("first").model_dump(mode="json"))])

    session.execute = execute
    repo = _repo_with_session(session)

    found = await repo.get_many(THREAD_ID, [wanted, other])

    assert found == {wanted: _evidence("first")}
    compiled = statements[0].compile(compile_kwargs={"literal_binds": True})
    sql = str(compiled).lower()
    assert "knowledge_evidence.thread_id =" in sql
    assert THREAD_ID.hex in sql.replace("-", "")
    assert "knowledge_evidence.id in" in sql


@pytest.mark.asyncio
async def test_get_many_skips_rows_that_no_longer_validate() -> None:
    good, bad = uuid4(), uuid4()
    session = MagicMock()
    session.execute = AsyncMock(
        return_value=_Rows(
            [
                (good, _evidence().model_dump(mode="json")),
                (bad, {"schema_version": 99, "kind": "document"}),
            ]
        )
    )
    repo = _repo_with_session(session)

    found = await repo.get_many(THREAD_ID, [good, bad])

    assert list(found) == [good]


@pytest.mark.asyncio
async def test_get_many_without_ids_does_not_query() -> None:
    session = MagicMock()
    session.execute = AsyncMock()
    repo = _repo_with_session(session)

    assert await repo.get_many(THREAD_ID, []) == {}
    session.execute.assert_not_awaited()
