"""Use cases for versioned documents: create, edit, rewrite, user edit, restore, export.

Every mutation goes through one fixed pipeline:
validate content → validate diagrams → render → store → move head (conditional).

The head move is optimistic: ``_head`` rejects a stale base up front so the
common conflict costs no rendering, and the repository re-checks the base
atomically. When another writer wins between the two checks, the file we just
stored is referenced by nothing, so it is deleted before the conflict surfaces.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

from core.exceptions.authored_documents import (
    DocumentNotFoundError,
    NoChangeError,
    RevisionConflictError,
    RevisionNotFoundError,
    UnsupportedFormatChangeError,
)
from core.types.authored_documents import (
    Actor,
    AuthoredDocument,
    DiagramCheck,
    DocumentKind,
    EditOp,
    GenerationPhase,
    Operation,
    Revision,
    RevisionDraft,
    RevisionResult,
    RevisionStats,
    RevisionSummary,
    SourceFormat,
    StoredFileRef,
)
from service.authored_documents.edit_engine import apply_edits
from service.authored_documents.formats import (
    ensure_edits_within_limits,
    ensure_format_change,
    ensure_valid_content,
    ensure_within_limits,
    filename_stem,
    kind_for_format,
    source_format_for,
)
from service.authored_documents.options_patch import merge_options, normalize_options
from service.authored_documents.progress import NULL_PROGRESS, ProgressSink
from service.authored_documents.revision_stats import compute_stats
from service.documents.naming import sanitize_filename

if TYPE_CHECKING:
    # ``service.documents.rendering`` imports this package, so it is only
    # imported at runtime inside ``__init__`` (see the default renderer below).
    from service.documents.rendering import RenderedDocument

_EXPORT_CACHE_SIZE = 32

_ExportKey = tuple[str, str, str | None, str]


@dataclass(frozen=True)
class _CachedExport:
    """Owner-neutral render output: the key has no filename, so none is cached."""

    data: bytes
    mime_type: str


class AuthoredDocumentRepositoryPort(Protocol):
    """Persistence port; ``get_revision``/``list_revisions`` are not user-scoped."""

    async def create(
        self, *, actor: Actor, kind: DocumentKind, draft: RevisionDraft, rendered_file_id: str
    ) -> tuple[AuthoredDocument, Revision]: ...

    async def append_revision(
        self,
        *,
        document_id: UUID,
        user_id: str,
        base_revision_no: int,
        actor: Actor,
        draft: RevisionDraft,
        rendered_file_id: str,
    ) -> tuple[AuthoredDocument, Revision]: ...

    async def get_document(self, document_id: UUID, user_id: str) -> AuthoredDocument | None: ...

    async def get_revision(self, document_id: UUID, revision_no: int) -> Revision | None: ...

    async def list_revisions(self, document_id: UUID) -> list[RevisionSummary]: ...

    async def list_for_thread(self, thread_id: UUID, user_id: str) -> list[AuthoredDocument]: ...

    async def find_by_rendered_file(
        self, file_id: str, user_id: str
    ) -> tuple[AuthoredDocument, RevisionSummary] | None: ...


class RenderedFileStorePort(Protocol):
    async def save(
        self, *, data: bytes, filename: str, mime_type: str, user_id: str, thread_id: str | None
    ) -> StoredFileRef: ...

    async def delete(self, file_id: str, user_id: str) -> None: ...


class DocumentRendererPort(Protocol):
    async def render(
        self,
        *,
        source_format: SourceFormat,
        format: str,
        filename: str,
        title: str | None,
        content: str,
        options: dict[str, Any],
        attachment_images: Mapping[str, bytes] | None = None,
    ) -> RenderedDocument: ...


class AttachmentResolverPort(Protocol):
    async def resolve(
        self, user_id: str, content: str, source_format: SourceFormat, *, strict: bool
    ) -> dict[str, bytes]: ...


class DiagramValidatorPort(Protocol):
    async def check(self, content: str, source_format: SourceFormat) -> DiagramCheck: ...


def _same_output(draft: RevisionDraft, head: Revision) -> bool:
    """True when committing ``draft`` would reproduce ``head`` byte-for-byte."""
    return (
        draft.content == head.content
        and draft.options == head.options
        and draft.title == head.title
        and draft.filename == head.filename
        and draft.format == head.format
    )


class AuthoredDocumentService:
    def __init__(
        self,
        *,
        repository: AuthoredDocumentRepositoryPort | None = None,
        file_store: RenderedFileStorePort | None = None,
        renderer: DocumentRendererPort | None = None,
        validator: DiagramValidatorPort | None = None,
        attachments: AttachmentResolverPort | None = None,
    ) -> None:
        # Defaults are imported lazily so tests (and the architecture check)
        # never pull the database or diagram worker in through this module.
        if repository is None:
            from infrastructure.db.persistence_gateway import authored_document_repository

            repository = authored_document_repository()
        if file_store is None:
            from service.storage.rendered_file_store import RenderedFileStore

            file_store = RenderedFileStore()
        if renderer is None:
            from service.documents.rendering import DocumentRenderer

            renderer = DocumentRenderer()
        if validator is None:
            from service.authored_documents.diagram_validation import DiagramValidator

            validator = DiagramValidator()
        if attachments is None:
            from service.authored_documents.attachments import AttachmentResolver

            attachments = AttachmentResolver()
        self._attachments = attachments
        self._repository = repository
        self._file_store = file_store
        self._renderer = renderer
        self._validator = validator
        self._exports: OrderedDict[_ExportKey, _CachedExport] = OrderedDict()

    # -- queries ---------------------------------------------------------

    async def get_document(self, user_id: str, document_id: UUID) -> AuthoredDocument:
        document = await self._repository.get_document(document_id, user_id)
        if document is None:
            raise DocumentNotFoundError(document_id)
        return document

    async def get_revision(self, user_id: str, document_id: UUID, revision_no: int) -> Revision:
        # The repository lookup is not user-scoped; ownership is enforced here.
        await self.get_document(user_id, document_id)
        revision = await self._repository.get_revision(document_id, revision_no)
        if revision is None:
            raise RevisionNotFoundError(document_id, revision_no)
        return revision

    async def list_revisions(self, user_id: str, document_id: UUID) -> list[RevisionSummary]:
        await self.get_document(user_id, document_id)
        return await self._repository.list_revisions(document_id)

    async def list_for_thread(self, user_id: str, thread_id: UUID) -> list[AuthoredDocument]:
        return await self._repository.list_for_thread(thread_id, user_id)

    async def find_by_rendered_file(
        self, user_id: str, file_id: str
    ) -> tuple[AuthoredDocument, RevisionSummary] | None:
        return await self._repository.find_by_rendered_file(file_id, user_id)

    # -- mutations -------------------------------------------------------

    async def create(
        self,
        actor: Actor,
        *,
        filename: str,
        format: str,
        content: str,
        title: str | None = None,
        options: dict[str, Any] | str | None = None,
        summary: str = "",
        progress: ProgressSink = NULL_PROGRESS,
    ) -> RevisionResult:
        kind = kind_for_format(format)
        source_format = source_format_for(format)
        ensure_within_limits(content, summary)
        draft = RevisionDraft(
            source_format=source_format,
            content=content,
            options=normalize_options(kind, options),
            title=title,
            filename=sanitize_filename(filename_stem(filename), format),
            format=format,
            operation=Operation.CREATE,
            summary=summary,
            stats=await self._stats("", content, source_format),
        )
        check, stored = await self._prepare(actor, draft, progress)
        document, revision = await self._repository.create(
            actor=actor, kind=kind, draft=draft, rendered_file_id=stored.file_id
        )
        return RevisionResult(document, revision, stored, check)

    async def edit(
        self,
        actor: Actor,
        document_id: UUID,
        *,
        base_revision_no: int,
        edits: Sequence[EditOp],
        summary: str,
        title: str | None = None,
        options_patch: dict[str, Any] | None = None,
        format: str | None = None,
        filename: str | None = None,
        progress: ProgressSink = NULL_PROGRESS,
    ) -> RevisionResult:
        ensure_within_limits(None, summary)
        ensure_edits_within_limits(edits)
        document, head = await self._head(actor, document_id, base_revision_no)
        target_format = format or head.format
        ensure_format_change(head.format, target_format, content_replaced=False)
        progress.phase(GenerationPhase.APPLYING, applied=0, total=len(edits))
        # The closest-snippet search is quadratic, so it runs off the event loop.
        content = await asyncio.to_thread(apply_edits, head.content, edits) if edits else head.content
        draft = await self._next_draft(
            head,
            content=content,
            operation=Operation.EDIT,
            summary=summary,
            title=title,
            options=merge_options(document.kind, head.options, options_patch),
            target_format=target_format,
            filename=filename,
            edit_ops=tuple(edits),
        )
        progress.phase(GenerationPhase.APPLYING, applied=len(edits), total=len(edits), changes=draft.stats.changes)
        return await self._commit(actor, document, draft, base_revision_no, progress)

    async def rewrite(
        self,
        actor: Actor,
        document_id: UUID,
        *,
        base_revision_no: int,
        content: str,
        summary: str,
        title: str | None = None,
        options: dict[str, Any] | str | None = None,
        format: str | None = None,
        filename: str | None = None,
        progress: ProgressSink = NULL_PROGRESS,
    ) -> RevisionResult:
        ensure_within_limits(content, summary)
        document, head = await self._head(actor, document_id, base_revision_no)
        target_format = format or head.format
        ensure_format_change(head.format, target_format, content_replaced=True)
        resolved_options = normalize_options(document.kind, options) if options is not None else head.options
        draft = await self._next_draft(
            head,
            content=content,
            operation=Operation.REWRITE,
            summary=summary,
            title=title,
            options=resolved_options,
            target_format=target_format,
            filename=filename,
        )
        return await self._commit(actor, document, draft, base_revision_no, progress)

    async def save_user_edit(
        self, actor: Actor, document_id: UUID, *, base_revision_no: int, content: str, summary: str = ""
    ) -> RevisionResult:
        ensure_within_limits(content, summary)
        document, head = await self._head(actor, document_id, base_revision_no)
        draft = await self._next_draft(
            head,
            content=content,
            operation=Operation.USER_EDIT,
            summary=summary,
            title=None,
            options=head.options,
            target_format=head.format,
            filename=None,
        )
        return await self._commit(actor, document, draft, base_revision_no, NULL_PROGRESS)

    async def restore(
        self, actor: Actor, document_id: UUID, *, revision_no: int, base_revision_no: int
    ) -> RevisionResult:
        document, head = await self._head(actor, document_id, base_revision_no)
        source = await self.get_revision(actor.user_id, document_id, revision_no)
        draft = RevisionDraft(
            source_format=source.source_format,
            content=source.content,
            options=source.options,
            title=source.title,
            filename=source.filename,
            format=source.format,
            operation=Operation.RESTORE,
            summary=f"restored draft {revision_no}",
            stats=await self._stats(head.content, source.content, source.source_format),
            restored_from_revision_no=revision_no,
        )
        if _same_output(draft, head):
            raise NoChangeError()
        return await self._commit(actor, document, draft, base_revision_no, NULL_PROGRESS)

    async def export(self, user_id: str, document_id: UUID, revision_no: int, format: str) -> RenderedDocument:
        """Render a revision in another format of the same kind, without saving it.

        Only formats that read the revision's source format are allowed, so a
        Markdown draft cannot be exported as ``json`` and vice versa.
        """
        document = await self.get_document(user_id, document_id)
        revision = await self.get_revision(user_id, document_id, revision_no)
        if kind_for_format(format) is not document.kind or source_format_for(format) is not revision.source_format:
            raise UnsupportedFormatChangeError(revision.format, format)
        key: _ExportKey = (
            revision.content_sha256,
            json.dumps(revision.options, sort_keys=True),
            revision.title,
            format,
        )
        filename = sanitize_filename(filename_stem(revision.filename), format)
        cached = self._exports.get(key)
        if cached is not None:
            from service.documents.rendering import RenderedDocument

            self._exports.move_to_end(key)
            return RenderedDocument(data=cached.data, mime_type=cached.mime_type, filename=filename)
        attachment_images = await self._attachments.resolve(
            user_id, revision.content, revision.source_format, strict=False
        )
        rendered = await self._renderer.render(
            source_format=revision.source_format,
            format=format,
            filename=filename,
            title=revision.title,
            content=revision.content,
            options=revision.options,
            attachment_images=attachment_images,
        )
        if not rendered.diagrams_complete:
            # A diagram fell back to source code (renderer down or timed out);
            # the next export should retry instead of serving this degraded file.
            return rendered
        self._exports[key] = _CachedExport(rendered.data, rendered.mime_type)
        while len(self._exports) > _EXPORT_CACHE_SIZE:
            self._exports.popitem(last=False)
        return rendered

    # -- pipeline --------------------------------------------------------

    async def _head(self, actor: Actor, document_id: UUID, base_revision_no: int) -> tuple[AuthoredDocument, Revision]:
        document = await self.get_document(actor.user_id, document_id)
        if document.head_revision_no != base_revision_no:
            raise RevisionConflictError(
                document_id=document_id,
                base_revision_no=base_revision_no,
                head_revision_no=document.head_revision_no,
            )
        head = await self.get_revision(actor.user_id, document_id, base_revision_no)
        return document, head

    async def _next_draft(
        self,
        head: Revision,
        *,
        content: str,
        operation: Operation,
        summary: str,
        title: str | None,
        options: dict[str, Any],
        target_format: str,
        filename: str | None,
        edit_ops: tuple[EditOp, ...] = (),
    ) -> RevisionDraft:
        ensure_within_limits(content, summary)
        source_format = source_format_for(target_format)
        base_name = filename_stem(filename or head.filename)
        draft = RevisionDraft(
            source_format=source_format,
            content=content,
            options=options,
            title=title if title is not None else head.title,
            filename=sanitize_filename(base_name, target_format),
            format=target_format,
            operation=operation,
            summary=summary,
            stats=await self._stats(head.content, content, source_format),
            edit_ops=edit_ops,
        )
        if _same_output(draft, head):
            raise NoChangeError()
        return draft

    @staticmethod
    async def _stats(old: str, new: str, source_format: SourceFormat) -> RevisionStats:
        # Two exact difflib passes are quadratic in the worst case; keep them off the loop.
        return await asyncio.to_thread(compute_stats, old, new, source_format)

    async def _prepare(
        self, actor: Actor, draft: RevisionDraft, progress: ProgressSink
    ) -> tuple[DiagramCheck, StoredFileRef]:
        ensure_valid_content(draft.source_format, draft.content)
        progress.phase(GenerationPhase.VALIDATING)
        check = await self._validator.check(draft.content, draft.source_format)
        attachment_images = await self._attachments.resolve(
            actor.user_id, draft.content, draft.source_format, strict=True
        )
        progress.phase(GenerationPhase.RENDERING)
        rendered = await self._renderer.render(
            source_format=draft.source_format,
            format=draft.format,
            filename=draft.filename,
            title=draft.title,
            content=draft.content,
            options=draft.options,
            attachment_images=attachment_images,
        )
        stored = await self._file_store.save(
            data=rendered.data,
            filename=rendered.filename,
            mime_type=rendered.mime_type,
            user_id=actor.user_id,
            thread_id=str(actor.thread_id) if actor.thread_id else None,
        )
        return check, stored

    async def _commit(
        self,
        actor: Actor,
        document: AuthoredDocument,
        draft: RevisionDraft,
        base_revision_no: int,
        progress: ProgressSink,
    ) -> RevisionResult:
        check, stored = await self._prepare(actor, draft, progress)
        try:
            updated, revision = await self._repository.append_revision(
                document_id=document.id,
                user_id=actor.user_id,
                base_revision_no=base_revision_no,
                actor=actor,
                draft=draft,
                rendered_file_id=stored.file_id,
            )
        except RevisionConflictError:
            # Only a lost race proves no revision references the file; other
            # failures may have committed, so their file is left in place.
            await self._file_store.delete(stored.file_id, actor.user_id)
            raise
        return RevisionResult(updated, revision, stored, check)


_service: AuthoredDocumentService | None = None


def get_authored_document_service() -> AuthoredDocumentService:
    """Process-wide instance, so the diagram and export caches are shared."""
    global _service
    if _service is None:
        _service = AuthoredDocumentService()
    return _service
