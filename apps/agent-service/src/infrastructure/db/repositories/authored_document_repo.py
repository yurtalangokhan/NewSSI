"""Repository for authored documents and their append-only revisions."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import load_only

from core.exceptions.authored_documents import DocumentNotFoundError, RevisionConflictError
from core.types.authored_documents import (
    Actor,
    AuthoredDocument,
    AuthorType,
    DocumentKind,
    EditOp,
    Operation,
    Revision,
    RevisionDraft,
    RevisionStats,
    RevisionSummary,
    SourceFormat,
)
from infrastructure.db.models.authored_document import AuthoredDocumentModel, AuthoredDocumentRevisionModel
from infrastructure.db.repositories.base import BaseRepository

# Summaries never read the heavy columns (content, options, edit_ops), so they
# are not fetched: a long history would otherwise pull every full snapshot.
_SUMMARY_COLUMNS = load_only(
    AuthoredDocumentRevisionModel.id,
    AuthoredDocumentRevisionModel.document_id,
    AuthoredDocumentRevisionModel.revision_no,
    AuthoredDocumentRevisionModel.operation,
    AuthoredDocumentRevisionModel.author_type,
    AuthoredDocumentRevisionModel.author_id,
    AuthoredDocumentRevisionModel.summary,
    AuthoredDocumentRevisionModel.stats,
    AuthoredDocumentRevisionModel.format,
    AuthoredDocumentRevisionModel.rendered_file_id,
    AuthoredDocumentRevisionModel.created_at,
)


class AuthoredDocumentRepository(BaseRepository):
    """Versioned, append-only documents with an optimistic (conditional) head move."""

    async def create(
        self, *, actor: Actor, kind: DocumentKind, draft: RevisionDraft, rendered_file_id: str
    ) -> tuple[AuthoredDocument, Revision]:
        async with self._session() as session:
            document = AuthoredDocumentModel(
                user_id=actor.user_id,
                thread_id=actor.thread_id,
                project_id=actor.project_id,
                kind=kind.value,
                title=draft.title,
                filename=draft.filename,
                format=draft.format,
                head_revision_no=1,
            )
            session.add(document)
            await session.flush()
            revision = _revision_model(document.id, 1, None, None, actor, draft, rendered_file_id)
            session.add(revision)
            await session.flush()
            return _to_document(document), _to_revision(revision)

    async def append_revision(
        self,
        *,
        document_id: UUID,
        user_id: str,
        base_revision_no: int,
        actor: Actor,
        draft: RevisionDraft,
        rendered_file_id: str,
    ) -> tuple[AuthoredDocument, Revision]:
        """Conditionally move the head forward one revision.

        The ``UPDATE ... WHERE head_revision_no == base_revision_no`` is the
        optimistic lock: it succeeds only if nothing moved the head since the
        caller read it. A miss disambiguates into a conflict (document exists,
        head moved) or a not-found (no such document for this user).
        """
        async with self._session() as session:
            result = await session.execute(
                update(AuthoredDocumentModel)
                .where(
                    AuthoredDocumentModel.id == document_id,
                    AuthoredDocumentModel.user_id == user_id,
                    AuthoredDocumentModel.head_revision_no == base_revision_no,
                )
                .values(
                    head_revision_no=base_revision_no + 1,
                    title=draft.title,
                    filename=draft.filename,
                    format=draft.format,
                    updated_at=func.now(),
                )
                .returning(AuthoredDocumentModel)
                # populate_existing: a document already loaded in this session
                # must be refreshed with the values this UPDATE just wrote.
                .execution_options(synchronize_session=False, populate_existing=True)
            )
            document = result.scalar_one_or_none()
            if document is None:
                head = await session.scalar(
                    select(AuthoredDocumentModel.head_revision_no).where(
                        AuthoredDocumentModel.id == document_id, AuthoredDocumentModel.user_id == user_id
                    )
                )
                if head is None:
                    raise DocumentNotFoundError(document_id)
                raise RevisionConflictError(
                    document_id=document_id, base_revision_no=base_revision_no, head_revision_no=head
                )
            parent_id = await session.scalar(_revision_id(document_id, base_revision_no))
            restored_id = (
                await session.scalar(_revision_id(document_id, draft.restored_from_revision_no))
                if draft.restored_from_revision_no
                else None
            )
            revision = _revision_model(
                document_id, base_revision_no + 1, parent_id, restored_id, actor, draft, rendered_file_id
            )
            session.add(revision)
            try:
                await session.flush()
            except IntegrityError:
                # The unique constraint on (document_id, revision_no) means
                # another writer took this revision number between our UPDATE
                # and this insert: that is the same conflict, reported the same
                # way, so the caller can refresh and retry.
                await session.rollback()
                head = await session.scalar(
                    select(AuthoredDocumentModel.head_revision_no).where(
                        AuthoredDocumentModel.id == document_id,
                        AuthoredDocumentModel.user_id == user_id,
                    )
                )
                raise RevisionConflictError(
                    document_id=document_id,
                    base_revision_no=base_revision_no,
                    head_revision_no=head if head is not None else base_revision_no + 1,
                ) from None
            return _to_document(document), _to_revision(revision)

    async def get_document(self, document_id: UUID, user_id: str) -> AuthoredDocument | None:
        async with self._read_session() as session:
            row = await session.scalar(
                select(AuthoredDocumentModel).where(
                    AuthoredDocumentModel.id == document_id, AuthoredDocumentModel.user_id == user_id
                )
            )
            return _to_document(row) if row else None

    async def get_revision(self, document_id: UUID, revision_no: int) -> Revision | None:
        async with self._read_session() as session:
            row = await session.scalar(
                select(AuthoredDocumentRevisionModel).where(
                    AuthoredDocumentRevisionModel.document_id == document_id,
                    AuthoredDocumentRevisionModel.revision_no == revision_no,
                )
            )
            return _to_revision(row) if row else None

    async def list_revisions(self, document_id: UUID) -> list[RevisionSummary]:
        async with self._read_session() as session:
            rows = (
                await session.scalars(
                    select(AuthoredDocumentRevisionModel)
                    .where(AuthoredDocumentRevisionModel.document_id == document_id)
                    .options(_SUMMARY_COLUMNS)
                    .order_by(AuthoredDocumentRevisionModel.revision_no)
                )
            ).all()
            return [_to_summary(row) for row in rows]

    async def list_for_thread(self, thread_id: UUID, user_id: str) -> list[AuthoredDocument]:
        async with self._read_session() as session:
            rows = (
                await session.scalars(
                    select(AuthoredDocumentModel)
                    .where(AuthoredDocumentModel.thread_id == thread_id, AuthoredDocumentModel.user_id == user_id)
                    .order_by(AuthoredDocumentModel.updated_at.desc())
                )
            ).all()
            return [_to_document(row) for row in rows]

    async def find_by_rendered_file(
        self, file_id: str, user_id: str
    ) -> tuple[AuthoredDocument, RevisionSummary] | None:
        async with self._read_session() as session:
            row = (
                await session.execute(
                    select(AuthoredDocumentModel, AuthoredDocumentRevisionModel)
                    .join(
                        AuthoredDocumentRevisionModel,
                        AuthoredDocumentRevisionModel.document_id == AuthoredDocumentModel.id,
                    )
                    .where(
                        AuthoredDocumentRevisionModel.rendered_file_id == file_id,
                        AuthoredDocumentModel.user_id == user_id,
                    )
                    .options(_SUMMARY_COLUMNS)
                    # Newest first: a restored revision can reuse an earlier
                    # file id, and the newest revision is the one the file
                    # currently shows.
                    .order_by(AuthoredDocumentRevisionModel.revision_no.desc())
                )
            ).first()
            return (_to_document(row[0]), _to_summary(row[1])) if row else None


def _revision_id(document_id: UUID, revision_no: int | None) -> Any:
    return select(AuthoredDocumentRevisionModel.id).where(
        AuthoredDocumentRevisionModel.document_id == document_id,
        AuthoredDocumentRevisionModel.revision_no == revision_no,
    )


def _revision_model(
    document_id: UUID,
    revision_no: int,
    parent_id: UUID | None,
    restored_id: UUID | None,
    actor: Actor,
    draft: RevisionDraft,
    rendered_file_id: str,
) -> AuthoredDocumentRevisionModel:
    return AuthoredDocumentRevisionModel(
        document_id=document_id,
        revision_no=revision_no,
        parent_revision_id=parent_id,
        restored_from_revision_id=restored_id,
        source_format=draft.source_format.value,
        content=draft.content,
        options=draft.options,
        title=draft.title,
        filename=draft.filename,
        format=draft.format,
        content_sha256=draft.content_sha256,
        operation=draft.operation.value,
        author_type=actor.author_type.value,
        author_id=actor.author_id,
        summary=draft.summary,
        edit_ops=[op.to_dict() for op in draft.edit_ops] or None,
        stats=draft.stats.to_dict(),
        rendered_file_id=rendered_file_id,
        tool_call_id=actor.tool_call_id,
        run_id=actor.run_id,
    )


def _to_document(row: AuthoredDocumentModel) -> AuthoredDocument:
    return AuthoredDocument(
        id=row.id,
        user_id=row.user_id,
        thread_id=row.thread_id,
        project_id=row.project_id,
        kind=DocumentKind(row.kind),
        title=row.title,
        filename=row.filename,
        format=row.format,
        head_revision_no=row.head_revision_no,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _summary_fields(row: AuthoredDocumentRevisionModel) -> dict[str, Any]:
    return {
        "id": row.id,
        "document_id": row.document_id,
        "revision_no": row.revision_no,
        "operation": Operation(row.operation),
        "author_type": AuthorType(row.author_type),
        "author_id": row.author_id,
        "summary": row.summary,
        "stats": RevisionStats.from_dict(row.stats),
        "format": row.format,
        "rendered_file_id": row.rendered_file_id,
        "created_at": row.created_at,
    }


def _to_summary(row: AuthoredDocumentRevisionModel) -> RevisionSummary:
    return RevisionSummary(**_summary_fields(row))


def _to_revision(row: AuthoredDocumentRevisionModel) -> Revision:
    return Revision(
        **_summary_fields(row),
        parent_revision_id=row.parent_revision_id,
        restored_from_revision_id=row.restored_from_revision_id,
        source_format=SourceFormat(row.source_format),
        content=row.content,
        options=dict(row.options or {}),
        title=row.title,
        filename=row.filename,
        content_sha256=row.content_sha256,
        edit_ops=tuple(EditOp(**op) for op in (row.edit_ops or [])),
    )
