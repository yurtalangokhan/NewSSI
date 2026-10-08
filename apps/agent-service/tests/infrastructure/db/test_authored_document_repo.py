from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from core.exceptions.authored_documents import DocumentNotFoundError, RevisionConflictError
from core.types.authored_documents import (
    Actor,
    AuthorType,
    DocumentKind,
    Operation,
    RevisionDraft,
    RevisionStats,
    SourceFormat,
)
from infrastructure.db.models.authored_document import AuthoredDocumentModel, AuthoredDocumentRevisionModel
from infrastructure.db.repositories.authored_document_repo import AuthoredDocumentRepository

ACTOR = Actor(user_id="u1", author_type=AuthorType.AGENT, author_id="persona-7", thread_id=uuid4())


def _draft(content: str = "# T") -> RevisionDraft:
    return RevisionDraft(
        source_format=SourceFormat.MARKDOWN,
        content=content,
        options={},
        title="T",
        filename="t.docx",
        format="docx",
        operation=Operation.CREATE,
        summary="created",
        stats=RevisionStats(),
    )


def _repo(session: Any) -> AuthoredDocumentRepository:
    repo = AuthoredDocumentRepository()

    @asynccontextmanager
    async def fake():
        yield session

    repo._session = fake  # type: ignore[method-assign]
    repo._read_session = fake  # type: ignore[method-assign]
    return repo


def _stamp(model: Any) -> None:
    now = datetime.now(UTC)
    for attr in ("created_at", "updated_at"):
        if hasattr(model, attr) and getattr(model, attr) is None:
            setattr(model, attr, now)
    if getattr(model, "id", None) is None:
        model.id = uuid4()


@pytest.mark.asyncio
async def test_create_persists_document_and_first_revision() -> None:
    session = MagicMock()
    session.add.side_effect = _stamp
    session.flush = AsyncMock()
    document, revision = await _repo(session).create(
        actor=ACTOR, kind=DocumentKind.DOCUMENT, draft=_draft(), rendered_file_id="f1"
    )
    added = [call.args[0] for call in session.add.call_args_list]
    assert isinstance(added[0], AuthoredDocumentModel) and added[0].head_revision_no == 1
    assert isinstance(added[1], AuthoredDocumentRevisionModel)
    assert added[1].revision_no == 1 and added[1].rendered_file_id == "f1"
    assert added[1].author_id == "persona-7" and added[1].operation == "create"
    assert document.head_revision_no == 1 and revision.revision_no == 1


@pytest.mark.asyncio
async def test_append_revision_moves_head_and_persists_revision() -> None:
    """Happy path: the conditional UPDATE hits, and the new revision links back
    to its parent and (when present) the revision it restores from.
    """
    document_id = uuid4()
    parent_id = uuid4()
    restored_id = uuid4()
    now = datetime.now(UTC)
    document_row = AuthoredDocumentModel(
        id=document_id,
        user_id="u1",
        thread_id=ACTOR.thread_id,
        project_id=None,
        kind=DocumentKind.DOCUMENT.value,
        title="T",
        filename="t.docx",
        format="docx",
        head_revision_no=3,
        created_at=now,
        updated_at=now,
    )
    update_result = MagicMock()
    update_result.scalar_one_or_none.return_value = document_row

    session = MagicMock()
    session.execute = AsyncMock(return_value=update_result)
    session.scalar = AsyncMock(side_effect=[parent_id, restored_id])
    session.flush = AsyncMock()

    draft = replace(_draft(), restored_from_revision_no=5)
    document, revision = await _repo(session).append_revision(
        document_id=document_id,
        user_id="u1",
        base_revision_no=2,
        actor=ACTOR,
        draft=draft,
        rendered_file_id="f3",
    )

    # Returned document/revision reflect the moved head.
    assert document.head_revision_no == 3
    assert revision.revision_no == 3
    assert revision.parent_revision_id == parent_id
    assert revision.restored_from_revision_id == restored_id
    assert revision.rendered_file_id == "f3"

    # The persisted revision row carries the same linkage.
    added = session.add.call_args_list[0].args[0]
    assert isinstance(added, AuthoredDocumentRevisionModel)
    assert added.revision_no == 3
    assert added.document_id == document_id
    assert added.parent_revision_id == parent_id
    assert added.restored_from_revision_id == restored_id
    assert added.rendered_file_id == "f3"

    # `session.scalar` was consulted for the parent lookup, then the restore lookup,
    # in that order — proves the "only when set" branch actually ran.
    assert session.scalar.await_count == 2

    # The UPDATE actually carries the optimistic-lock predicates and the head move,
    # not just "some update that happens to succeed".
    stmt = session.execute.call_args_list[0].args[0]
    compiled = stmt.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    params = compiled.params
    assert params["id_1"] == document_id
    assert params["user_id_1"] == "u1"
    assert params["head_revision_no_1"] == 2  # WHERE head_revision_no == base_revision_no
    assert params["head_revision_no"] == 3  # SET head_revision_no = base_revision_no + 1
    assert "updated_at=now()" in sql.replace(" ", "")


@pytest.mark.asyncio
async def test_append_revision_raises_conflict_when_head_moved() -> None:
    session = MagicMock()
    no_row = MagicMock()
    no_row.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=no_row)
    session.scalar = AsyncMock(return_value=3)
    with pytest.raises(RevisionConflictError) as caught:
        await _repo(session).append_revision(
            document_id=uuid4(),
            user_id="u1",
            base_revision_no=2,
            actor=ACTOR,
            draft=_draft(),
            rendered_file_id="f2",
        )
    assert caught.value.head_revision_no == 3
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_append_revision_maps_a_unique_violation_to_a_conflict() -> None:
    """A racing writer that took revision N first is the same conflict."""
    document_id = uuid4()
    parent_id = uuid4()
    now = datetime.now(UTC)
    document_row = AuthoredDocumentModel(
        id=document_id,
        user_id="u1",
        thread_id=ACTOR.thread_id,
        project_id=None,
        kind=DocumentKind.DOCUMENT.value,
        title="T",
        filename="t.docx",
        format="docx",
        head_revision_no=3,
        created_at=now,
        updated_at=now,
    )
    update_result = MagicMock()
    update_result.scalar_one_or_none.return_value = document_row

    session = MagicMock()
    session.execute = AsyncMock(return_value=update_result)
    session.scalar = AsyncMock(side_effect=[parent_id, 4])
    session.flush = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("duplicate key")))
    session.rollback = AsyncMock()

    with pytest.raises(RevisionConflictError) as caught:
        await _repo(session).append_revision(
            document_id=document_id,
            user_id="u1",
            base_revision_no=2,
            actor=ACTOR,
            draft=_draft(),
            rendered_file_id="f3",
        )

    assert caught.value.head_revision_no == 4
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_append_revision_on_missing_document_is_not_found() -> None:
    session = MagicMock()
    no_row = MagicMock()
    no_row.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=no_row)
    session.scalar = AsyncMock(return_value=None)
    with pytest.raises(DocumentNotFoundError):
        await _repo(session).append_revision(
            document_id=uuid4(),
            user_id="u1",
            base_revision_no=1,
            actor=ACTOR,
            draft=_draft(),
            rendered_file_id="f2",
        )


_HEAVY_COLUMNS = ("content", "options", "edit_ops")


def _assert_light(stmt: Any) -> None:
    import re

    sql = str(stmt.compile(dialect=postgresql.dialect()))
    for column in _HEAVY_COLUMNS:
        assert not re.search(rf"authored_document_revisions\.{column}\b", sql), column
    assert "authored_document_revisions.summary" in sql


@pytest.mark.asyncio
async def test_list_revisions_does_not_load_content_options_or_edit_ops() -> None:
    session = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = []
    session.scalars = AsyncMock(return_value=scalars)
    await _repo(session).list_revisions(uuid4())
    _assert_light(session.scalars.call_args.args[0])


@pytest.mark.asyncio
async def test_find_by_rendered_file_does_not_load_revision_content() -> None:
    session = MagicMock()
    result = MagicMock()
    result.first.return_value = None
    session.execute = AsyncMock(return_value=result)
    assert await _repo(session).find_by_rendered_file("f1", "u1") is None
    _assert_light(session.execute.call_args.args[0])
