from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from core.exceptions.authored_documents import (
    DocumentNotFoundError,
    EditApplicationError,
    InvalidDocumentContentError,
    NoChangeError,
    RevisionConflictError,
    RevisionNotFoundError,
    UnsupportedFormatChangeError,
)
from core.types.authored_documents import (
    Actor,
    AuthoredDocument,
    AuthorType,
    DiagramCheck,
    EditOp,
    GenerationPhase,
    Operation,
    Revision,
    StoredFileRef,
)
from service.authored_documents import get_authored_document_service
from service.authored_documents.service import AuthoredDocumentService
from service.documents.rendering import RenderedDocument

ACTOR = Actor(user_id="u1", author_type=AuthorType.AGENT, author_id="agent")
USER = Actor(user_id="u1", author_type=AuthorType.USER, author_id="u1")
STRANGER = Actor(user_id="u2", author_type=AuthorType.USER, author_id="u2")
NOW = datetime.now(UTC)


class FakeRepo:
    def __init__(self):
        self.docs: dict[UUID, AuthoredDocument] = {}
        self.revs: dict[tuple[UUID, int], Revision] = {}
        self.race_head: int | None = None  # simulate another writer winning

    def _rev(self, doc_id, no, actor, draft, file_id):
        return Revision(
            id=uuid4(),
            document_id=doc_id,
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

    async def create(self, *, actor, kind, draft, rendered_file_id):
        doc = AuthoredDocument(
            uuid4(), actor.user_id, actor.thread_id, None, kind, draft.title, draft.filename, draft.format, 1, NOW, NOW
        )
        self.docs[doc.id] = doc
        rev = self._rev(doc.id, 1, actor, draft, rendered_file_id)
        self.revs[(doc.id, 1)] = rev
        return doc, rev

    async def append_revision(self, *, document_id, user_id, base_revision_no, actor, draft, rendered_file_id):
        doc = self.docs[document_id]
        head = self.race_head or doc.head_revision_no
        if head != base_revision_no:
            raise RevisionConflictError(
                document_id=document_id, base_revision_no=base_revision_no, head_revision_no=head
            )
        doc = replace(
            doc, head_revision_no=base_revision_no + 1, filename=draft.filename, format=draft.format, title=draft.title
        )
        self.docs[document_id] = doc
        rev = self._rev(document_id, base_revision_no + 1, actor, draft, rendered_file_id)
        self.revs[(document_id, rev.revision_no)] = rev
        return doc, rev

    async def get_document(self, document_id, user_id):
        doc = self.docs.get(document_id)
        return doc if doc and doc.user_id == user_id else None

    async def get_revision(self, document_id, revision_no):
        return self.revs.get((document_id, revision_no))

    async def list_revisions(self, document_id):
        return [rev for (doc_id, _), rev in sorted(self.revs.items(), key=lambda i: i[0][1]) if doc_id == document_id]

    async def list_for_thread(self, thread_id, user_id):
        return [d for d in self.docs.values() if d.thread_id == thread_id and d.user_id == user_id]

    async def find_by_rendered_file(self, file_id, user_id):
        for (doc_id, _), rev in self.revs.items():
            doc = self.docs[doc_id]
            if rev.rendered_file_id == file_id and doc.user_id == user_id:
                return doc, rev
        return None


class FakeStore:
    def __init__(self):
        self.saved, self.deleted, self.thread_ids = [], [], []

    async def save(self, *, data, filename, mime_type, user_id, thread_id):
        file_id = f"f{len(self.saved) + 1}"
        self.saved.append(file_id)
        self.thread_ids.append(thread_id)
        return StoredFileRef(file_id, filename, mime_type, len(data), f"/api/chat/file/{file_id}?download=1")

    async def delete(self, file_id, user_id):
        self.deleted.append(file_id)


class FakeRenderer:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self.diagrams_complete = True

    async def render(self, *, source_format, format, filename, title, content, options, attachment_images=None):
        self.calls.append((format, filename))
        return RenderedDocument(content.encode(), "text/markdown", filename, self.diagrams_complete)


class FakeValidator:
    async def check(self, content, source_format):
        return DiagramCheck.NOT_APPLICABLE


class Progress:
    def __init__(self):
        self.events = []

    def phase(self, phase, **kw):
        self.events.append(phase)


def _service():
    repo, store, renderer = FakeRepo(), FakeStore(), FakeRenderer()
    service = AuthoredDocumentService(repository=repo, file_store=store, renderer=renderer, validator=FakeValidator())
    return service, repo, store, renderer


@pytest.mark.asyncio
async def test_create_then_edit_produces_draft_two_with_stats() -> None:
    service, _, _, _ = _service()
    created = await service.create(ACTOR, filename="r", format="md", content="# R\n\nA\n", title="R")
    progress = Progress()
    edited = await service.edit(
        ACTOR,
        created.document.id,
        base_revision_no=1,
        edits=[EditOp("A", "B")],
        summary="A→B",
        progress=progress,
    )
    assert edited.revision.revision_no == 2 and edited.revision.operation is Operation.EDIT
    assert edited.revision.content == "# R\n\nB\n"
    assert edited.revision.edit_ops == (EditOp("A", "B"),)
    assert (edited.revision.stats.added, edited.revision.stats.removed) == (1, 1)
    assert progress.events == [
        GenerationPhase.APPLYING,
        GenerationPhase.APPLYING,
        GenerationPhase.VALIDATING,
        GenerationPhase.RENDERING,
    ]
    assert created.document.filename == "r.md"
    assert created.revision.operation is Operation.CREATE
    assert created.diagram_check is DiagramCheck.NOT_APPLICABLE
    assert edited.file.file_id == "f2" and edited.revision.rendered_file_id == "f2"


@pytest.mark.asyncio
async def test_create_rejects_empty_content_before_storing() -> None:
    service, _, store, _ = _service()
    with pytest.raises(InvalidDocumentContentError):
        await service.create(ACTOR, filename="r", format="md", content="   ")
    assert store.saved == []


@pytest.mark.asyncio
async def test_create_passes_the_actor_thread_to_the_store() -> None:
    service, _, store, _ = _service()
    thread_id = uuid4()
    await service.create(replace(ACTOR, thread_id=thread_id), filename="r", format="md", content="A")
    assert store.thread_ids == [str(thread_id)]


@pytest.mark.asyncio
async def test_stale_base_is_rejected_before_rendering() -> None:
    service, _, store, _ = _service()
    created = await service.create(ACTOR, filename="r", format="md", content="A")
    await service.edit(ACTOR, created.document.id, base_revision_no=1, edits=[EditOp("A", "B")], summary="")
    with pytest.raises(RevisionConflictError):
        await service.edit(ACTOR, created.document.id, base_revision_no=1, edits=[EditOp("B", "C")], summary="")
    assert store.saved == ["f1", "f2"]


@pytest.mark.asyncio
async def test_lost_race_deletes_the_orphaned_render() -> None:
    service, repo, store, _ = _service()
    created = await service.create(ACTOR, filename="r", format="md", content="A")
    repo.race_head = 2  # another writer committed between our pre-check and our write
    original_get = repo.get_document

    async def stale_get(document_id, user_id):
        return replace(await original_get(document_id, user_id), head_revision_no=1)

    repo.get_document = stale_get
    with pytest.raises(RevisionConflictError):
        await service.save_user_edit(USER, created.document.id, base_revision_no=1, content="Z")
    assert store.deleted == ["f2"]


@pytest.mark.asyncio
async def test_failed_edit_saves_nothing_and_no_op_is_rejected() -> None:
    service, _, store, _ = _service()
    created = await service.create(ACTOR, filename="r", format="md", content="A")
    with pytest.raises(EditApplicationError):
        await service.edit(ACTOR, created.document.id, base_revision_no=1, edits=[EditOp("Q", "R")], summary="")
    with pytest.raises(NoChangeError):
        await service.edit(ACTOR, created.document.id, base_revision_no=1, edits=[], summary="")
    with pytest.raises(NoChangeError):
        await service.save_user_edit(USER, created.document.id, base_revision_no=1, content="A")
    assert store.saved == ["f1"]


@pytest.mark.asyncio
async def test_format_and_options_only_edit_and_cross_source_rules() -> None:
    service, _, _, _ = _service()
    created = await service.create(ACTOR, filename="rapor", format="docx", content="# R")
    edited = await service.edit(ACTOR, created.document.id, base_revision_no=1, edits=[], summary="pdf", format="pdf")
    assert (edited.document.format, edited.document.filename) == ("pdf", "rapor.pdf")
    with pytest.raises(UnsupportedFormatChangeError):
        await service.edit(ACTOR, created.document.id, base_revision_no=2, edits=[], summary="", format="json")
    with pytest.raises(UnsupportedFormatChangeError):
        await service.rewrite(ACTOR, created.document.id, base_revision_no=2, content="a", summary="", format="xlsx")
    rewritten = await service.rewrite(
        ACTOR, created.document.id, base_revision_no=2, content='{"a": 1}', summary="json", format="json"
    )
    assert rewritten.revision.source_format.value == "json"
    assert rewritten.revision.operation is Operation.REWRITE
    assert rewritten.document.filename == "rapor.json"


@pytest.mark.asyncio
async def test_options_patch_alone_creates_a_draft() -> None:
    service, _, _, _ = _service()
    created = await service.create(ACTOR, filename="r", format="pdf", content="# R")
    edited = await service.edit(
        ACTOR,
        created.document.id,
        base_revision_no=1,
        edits=[],
        summary="toc",
        options_patch={"toc": {"enabled": True}},
    )
    assert edited.revision.options == {"toc": {"enabled": True}}
    assert edited.revision.content == created.revision.content


@pytest.mark.asyncio
async def test_restore_copies_content_as_a_new_draft() -> None:
    service, _, _, _ = _service()
    created = await service.create(ACTOR, filename="r", format="md", content="A")
    await service.edit(ACTOR, created.document.id, base_revision_no=1, edits=[EditOp("A", "B")], summary="")
    restored = await service.restore(USER, created.document.id, revision_no=1, base_revision_no=2)
    assert restored.revision.revision_no == 3
    assert restored.revision.content == "A"
    assert restored.revision.operation is Operation.RESTORE


@pytest.mark.asyncio
async def test_restore_of_the_head_or_a_missing_draft_is_rejected() -> None:
    service, _, store, _ = _service()
    created = await service.create(ACTOR, filename="r", format="md", content="A")
    with pytest.raises(NoChangeError):
        await service.restore(USER, created.document.id, revision_no=1, base_revision_no=1)
    with pytest.raises(RevisionNotFoundError):
        await service.restore(USER, created.document.id, revision_no=9, base_revision_no=1)
    assert store.saved == ["f1"]


@pytest.mark.asyncio
async def test_other_users_cannot_read_or_change_a_document() -> None:
    service, _, store, _ = _service()
    created = await service.create(ACTOR, filename="r", format="md", content="A")
    doc_id = created.document.id
    with pytest.raises(DocumentNotFoundError):
        await service.get_revision(STRANGER.user_id, doc_id, 1)
    with pytest.raises(DocumentNotFoundError):
        await service.list_revisions(STRANGER.user_id, doc_id)
    with pytest.raises(DocumentNotFoundError):
        await service.save_user_edit(STRANGER, doc_id, base_revision_no=1, content="Z")
    with pytest.raises(DocumentNotFoundError):
        await service.export(STRANGER.user_id, doc_id, 1, "md")
    assert await service.find_by_rendered_file(STRANGER.user_id, "f1") is None
    assert store.saved == ["f1"]


@pytest.mark.asyncio
async def test_queries_delegate_to_the_repository() -> None:
    service, _, _, _ = _service()
    thread_id = uuid4()
    created = await service.create(replace(ACTOR, thread_id=thread_id), filename="r", format="md", content="A")
    doc_id = created.document.id
    await service.edit(ACTOR, doc_id, base_revision_no=1, edits=[EditOp("A", "B")], summary="")
    assert [r.revision_no for r in await service.list_revisions(ACTOR.user_id, doc_id)] == [1, 2]
    assert [d.id for d in await service.list_for_thread(ACTOR.user_id, thread_id)] == [doc_id]
    found = await service.find_by_rendered_file(ACTOR.user_id, "f2")
    assert found is not None and found[1].revision_no == 2
    with pytest.raises(RevisionNotFoundError):
        await service.get_revision(ACTOR.user_id, doc_id, 7)


@pytest.mark.asyncio
async def test_export_renders_same_kind_formats_and_caches_the_result() -> None:
    service, _, _, renderer = _service()
    created = await service.create(ACTOR, filename="rapor", format="md", content="# R")
    renderer.calls.clear()
    first = await service.export(ACTOR.user_id, created.document.id, 1, "pdf")
    second = await service.export(ACTOR.user_id, created.document.id, 1, "pdf")
    assert first.data == second.data and second.filename == "rapor.pdf"
    assert renderer.calls == [("pdf", "rapor.pdf")]
    with pytest.raises(UnsupportedFormatChangeError):
        await service.export(ACTOR.user_id, created.document.id, 1, "xlsx")
    with pytest.raises(UnsupportedFormatChangeError):
        await service.export(ACTOR.user_id, created.document.id, 1, "json")


@pytest.mark.asyncio
async def test_export_cache_evicts_the_least_recently_used_entry() -> None:
    service, _, _, renderer = _service()
    created = await service.create(ACTOR, filename="r", format="md", content="A0")
    doc_id = created.document.id
    for i in range(1, 33):  # 33 drafts in total, one more than the cache holds
        await service.save_user_edit(USER, doc_id, base_revision_no=i, content=f"A{i}")
    renderer.calls.clear()
    for no in range(1, 34):
        await service.export(ACTOR.user_id, doc_id, no, "md")
    assert len(renderer.calls) == 33
    await service.export(ACTOR.user_id, doc_id, 33, "md")  # most recent: cached
    await service.export(ACTOR.user_id, doc_id, 1, "md")  # oldest: evicted
    assert len(renderer.calls) == 34


def test_process_wide_instance_is_shared(monkeypatch: pytest.MonkeyPatch) -> None:
    import service.authored_documents.service as module

    monkeypatch.setattr(module, "_service", None)
    monkeypatch.setattr(
        module,
        "AuthoredDocumentService",
        lambda: AuthoredDocumentService(
            repository=FakeRepo(), file_store=FakeStore(), renderer=FakeRenderer(), validator=FakeValidator()
        ),
    )
    assert get_authored_document_service() is get_authored_document_service()


@pytest.mark.asyncio
async def test_known_format_extensions_are_not_doubled() -> None:
    service, _, _, renderer = _service()
    created = await service.create(ACTOR, filename="rapor.docx", format="docx", content="# R")
    assert created.document.filename == "rapor.docx"
    converted = await service.create(ACTOR, filename="rapor.docx", format="pdf", content="# R")
    assert converted.document.filename == "rapor.pdf"
    edited = await service.edit(
        ACTOR, created.document.id, base_revision_no=1, edits=[], summary="", format="pdf", filename="r.docx"
    )
    assert edited.document.filename == "r.pdf"
    renderer.calls.clear()
    exported = await service.export(ACTOR.user_id, created.document.id, 1, "md")
    assert exported.filename == "rapor.md"


@pytest.mark.asyncio
async def test_a_non_format_suffix_is_kept() -> None:
    service, _, _, _ = _service()
    created = await service.create(ACTOR, filename="plan v1.2", format="md", content="A")
    assert created.document.filename == "plan v1.2.md"
    edited = await service.edit(ACTOR, created.document.id, base_revision_no=1, edits=[], summary="", format="pdf")
    assert edited.document.filename == "plan v1.2.pdf"


@pytest.mark.asyncio
async def test_cached_export_carries_each_documents_own_filename() -> None:
    service, _, _, renderer = _service()
    mine = await service.create(ACTOR, filename="mine", format="md", content="# Same")
    theirs = await service.create(STRANGER, filename="theirs", format="md", content="# Same")
    renderer.calls.clear()
    first = await service.export(ACTOR.user_id, mine.document.id, 1, "pdf")
    second = await service.export(STRANGER.user_id, theirs.document.id, 1, "pdf")
    assert len(renderer.calls) == 1  # identical content shares the cached bytes
    assert (first.filename, second.filename) == ("mine.pdf", "theirs.pdf")


@pytest.mark.asyncio
async def test_degraded_exports_are_not_cached() -> None:
    service, _, _, renderer = _service()
    created = await service.create(ACTOR, filename="r", format="md", content="# R")
    renderer.calls.clear()
    renderer.diagrams_complete = False
    await service.export(ACTOR.user_id, created.document.id, 1, "pdf")
    renderer.diagrams_complete = True
    await service.export(ACTOR.user_id, created.document.id, 1, "pdf")
    await service.export(ACTOR.user_id, created.document.id, 1, "pdf")
    assert len(renderer.calls) == 2  # retried once, then cached


@pytest.mark.asyncio
async def test_export_of_a_stored_unsafe_diagram_never_reaches_the_png_renderer() -> None:
    from service.documents.diagram_images import DiagramImageService
    from service.documents.rendering import DocumentRenderer

    class SpyDiagrams:
        renderer_version = "spy"

        def __init__(self):
            self.rendered: list[str] = []

        async def validate(self, source):  # pragma: no cover
            return None

        async def render_png(self, source, *, scale=3.0):
            self.rendered.append(source)
            raise AssertionError("render_png must not be called for an unsafe source")

        async def aclose(self):  # pragma: no cover
            return None

    spy = SpyDiagrams()
    repo, store = FakeRepo(), FakeStore()
    service = AuthoredDocumentService(
        repository=repo,
        file_store=store,
        renderer=DocumentRenderer(DiagramImageService(renderer=spy, cache_size=4)),
        validator=FakeValidator(),  # a stored revision that skipped validation
    )
    content = '# T\n\n```mermaid\nflowchart LR\n  A@{ img: "/etc/passwd", label: "x" }\n```\n'
    created = await service.create(ACTOR, filename="r", format="md", content=content)

    rendered = await service.export(ACTOR.user_id, created.document.id, 1, "pdf")

    assert spy.rendered == [] and rendered.data.startswith(b"%PDF")
    assert rendered.diagrams_complete is False


@pytest.mark.asyncio
async def test_oversized_content_and_summary_are_rejected_before_any_work() -> None:
    from core.types.authored_documents import MAX_DOCUMENT_CONTENT_CHARS, MAX_REVISION_SUMMARY_CHARS

    service, _, store, renderer = _service()
    big = "x" * (MAX_DOCUMENT_CONTENT_CHARS + 1)
    with pytest.raises(InvalidDocumentContentError):
        await service.create(ACTOR, filename="r", format="md", content=big)
    with pytest.raises(InvalidDocumentContentError):
        await service.create(
            ACTOR, filename="r", format="md", content="# R", summary="s" * (MAX_REVISION_SUMMARY_CHARS + 1)
        )
    created = await service.create(ACTOR, filename="r", format="md", content="# R")
    with pytest.raises(InvalidDocumentContentError):
        await service.rewrite(ACTOR, created.document.id, base_revision_no=1, content=big, summary="s")
    with pytest.raises(InvalidDocumentContentError):
        await service.save_user_edit(USER, created.document.id, base_revision_no=1, content=big)
    assert store.saved == ["f1"] and len(renderer.calls) == 1


@pytest.mark.asyncio
async def test_edit_count_and_snippet_sizes_are_bounded() -> None:
    from core.types.authored_documents import MAX_EDIT_SNIPPET_CHARS, MAX_EDITS_PER_CALL

    service, _, _, _ = _service()
    created = await service.create(ACTOR, filename="r", format="md", content="# R")
    doc_id = created.document.id
    too_many = [EditOp("# R", "# S")] * (MAX_EDITS_PER_CALL + 1)
    with pytest.raises(InvalidDocumentContentError):
        await service.edit(ACTOR, doc_id, base_revision_no=1, edits=too_many, summary="s")
    huge = "z" * (MAX_EDIT_SNIPPET_CHARS + 1)
    with pytest.raises(InvalidDocumentContentError):
        await service.edit(ACTOR, doc_id, base_revision_no=1, edits=[EditOp(huge, "a")], summary="s")
    with pytest.raises(InvalidDocumentContentError):
        await service.edit(ACTOR, doc_id, base_revision_no=1, edits=[EditOp("# R", huge)], summary="s")


@pytest.mark.asyncio
async def test_stats_and_edit_diffing_run_off_the_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    import threading

    import service.authored_documents.service as module

    loop_thread = threading.get_ident()
    seen: dict[str, int] = {}

    def spy(name, real):
        def wrapper(*args, **kwargs):
            seen[name] = threading.get_ident()
            return real(*args, **kwargs)

        return wrapper

    monkeypatch.setattr(module, "compute_stats", spy("stats", module.compute_stats))
    monkeypatch.setattr(module, "apply_edits", spy("edits", module.apply_edits))
    service, _, _, _ = _service()
    created = await service.create(ACTOR, filename="r", format="md", content="# R")
    await service.edit(ACTOR, created.document.id, base_revision_no=1, edits=[EditOp("# R", "# S")], summary="s")

    assert seen["stats"] != loop_thread and seen["edits"] != loop_thread


@pytest.mark.asyncio
async def test_edit_result_past_the_content_limit_is_rejected() -> None:
    service, _, _, _ = _service()
    created = await service.create(ACTOR, filename="r", format="md", content="ab " * 20_000)
    grow = EditOp("ab ", "c" * 100, replace_all=True)
    with pytest.raises(InvalidDocumentContentError):
        await service.edit(ACTOR, created.document.id, base_revision_no=1, edits=[grow], summary="s")
