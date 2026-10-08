"""Shared fixtures for the agent tests: authored-document domain factories and
an in-memory draft service, so no document tool call reaches the database or
the Mermaid worker pool."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from core.exceptions.authored_documents import RevisionConflictError
from core.types.authored_documents import (
    Actor,
    AuthoredDocument,
    AuthorType,
    DiagramCheck,
    DocumentKind,
    Operation,
    Revision,
    RevisionDraft,
    RevisionResult,
    RevisionStats,
    RevisionSummary,
    SourceFormat,
    StoredFileRef,
)
from service.authored_documents.service import AuthoredDocumentService

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)


@pytest.fixture
def make_document():
    def factory(**overrides: Any) -> AuthoredDocument:
        fields: dict[str, Any] = dict(
            id=uuid4(),
            user_id="u1",
            thread_id=None,
            project_id=None,
            kind=DocumentKind.DOCUMENT,
            title="Rapor",
            filename="rapor.docx",
            format="docx",
            head_revision_no=1,
            created_at=NOW,
            updated_at=NOW,
        )
        return AuthoredDocument(**{**fields, **overrides})

    return factory


@pytest.fixture
def make_revision():
    def factory(**overrides: Any) -> Revision:
        fields: dict[str, Any] = dict(
            id=uuid4(),
            document_id=uuid4(),
            revision_no=1,
            operation=Operation.CREATE,
            author_type=AuthorType.AGENT,
            author_id="agent",
            summary="",
            stats=RevisionStats(),
            format="docx",
            rendered_file_id="f1",
            created_at=NOW,
            source_format=SourceFormat.MARKDOWN,
            content="# Rapor\n",
            options={},
            title="Rapor",
            filename="rapor.docx",
            content_sha256="0" * 64,
        )
        return Revision(**{**fields, **overrides})

    return factory


@pytest.fixture
def make_result(make_document, make_revision):
    def factory(revision_no: int = 1, operation: str = "create") -> RevisionResult:
        document = make_document(head_revision_no=revision_no)
        revision = make_revision(
            document_id=document.id,
            revision_no=revision_no,
            operation=Operation(operation),
            stats=RevisionStats(added=1, removed=1),
        )
        file = StoredFileRef(
            "f9",
            "rapor.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            10,
            "/api/chat/file/f9?download=1",
        )
        return RevisionResult(document, revision, file, DiagramCheck.PASSED)

    return factory


class InMemoryAuthoredDocumentRepository:
    """``AuthoredDocumentRepositoryPort`` over two dicts, for tool-level tests."""

    def __init__(self) -> None:
        self.documents: dict[UUID, AuthoredDocument] = {}
        self.revisions: dict[tuple[UUID, int], Revision] = {}

    def _revision(self, document_id: UUID, no: int, actor: Actor, draft: RevisionDraft, file_id: str) -> Revision:
        return Revision(
            id=uuid4(),
            document_id=document_id,
            revision_no=no,
            operation=draft.operation,
            author_type=actor.author_type,
            author_id=actor.author_id,
            summary=draft.summary,
            stats=draft.stats,
            format=draft.format,
            rendered_file_id=file_id,
            created_at=NOW,
            source_format=draft.source_format,
            content=draft.content,
            options=draft.options,
            title=draft.title,
            filename=draft.filename,
            content_sha256=draft.content_sha256,
            edit_ops=draft.edit_ops,
        )

    async def create(
        self, *, actor: Actor, kind: DocumentKind, draft: RevisionDraft, rendered_file_id: str
    ) -> tuple[AuthoredDocument, Revision]:
        document = AuthoredDocument(
            id=uuid4(),
            user_id=actor.user_id,
            thread_id=actor.thread_id,
            project_id=actor.project_id,
            kind=kind,
            title=draft.title,
            filename=draft.filename,
            format=draft.format,
            head_revision_no=1,
            created_at=NOW,
            updated_at=NOW,
        )
        revision = self._revision(document.id, 1, actor, draft, rendered_file_id)
        self.documents[document.id] = document
        self.revisions[(document.id, 1)] = revision
        return document, revision

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
        document = self.documents[document_id]
        if document.head_revision_no != base_revision_no:
            raise RevisionConflictError(
                document_id=document_id,
                base_revision_no=base_revision_no,
                head_revision_no=document.head_revision_no,
            )
        document = replace(
            document,
            head_revision_no=base_revision_no + 1,
            title=draft.title,
            filename=draft.filename,
            format=draft.format,
        )
        revision = self._revision(document_id, base_revision_no + 1, actor, draft, rendered_file_id)
        self.documents[document_id] = document
        self.revisions[(document_id, revision.revision_no)] = revision
        return document, revision

    async def get_document(self, document_id: UUID, user_id: str) -> AuthoredDocument | None:
        document = self.documents.get(document_id)
        return document if document and document.user_id == user_id else None

    async def get_revision(self, document_id: UUID, revision_no: int) -> Revision | None:
        return self.revisions.get((document_id, revision_no))

    async def list_revisions(self, document_id: UUID) -> list[RevisionSummary]:
        return [rev for (doc_id, _), rev in sorted(self.revisions.items(), key=lambda i: i[0][1]) if doc_id == document_id]

    async def list_for_thread(self, thread_id: UUID, user_id: str) -> list[AuthoredDocument]:
        return [d for d in self.documents.values() if d.thread_id == thread_id and d.user_id == user_id]

    async def find_by_rendered_file(self, file_id: str, user_id: str) -> tuple[AuthoredDocument, RevisionSummary] | None:
        for (doc_id, _), revision in self.revisions.items():
            document = self.documents[doc_id]
            if revision.rendered_file_id == file_id and document.user_id == user_id:
                return document, revision
        return None


class _NoDiagramValidator:
    """Skips the Mermaid worker pool; diagram checks have their own tests."""

    async def check(self, content: str, source_format: SourceFormat) -> DiagramCheck:
        return DiagramCheck.NOT_APPLICABLE


@pytest.fixture
def authored_document_repository() -> InMemoryAuthoredDocumentRepository:
    return InMemoryAuthoredDocumentRepository()


@pytest.fixture(autouse=True)
def authored_document_service(
    monkeypatch: pytest.MonkeyPatch, authored_document_repository: InMemoryAuthoredDocumentRepository
) -> AuthoredDocumentService:
    """The draft service the document tools see: real renderer and file store,
    in-memory drafts. Tests that need a stub service patch over this one."""
    service = AuthoredDocumentService(repository=authored_document_repository, validator=_NoDiagramValidator())
    monkeypatch.setattr("agents.tooling.document_tool_support.get_authored_document_service", lambda: service)
    return service
