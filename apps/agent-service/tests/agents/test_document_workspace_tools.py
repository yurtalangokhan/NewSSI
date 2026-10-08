"""The draft workspace seen from the model: list_documents, read_document, the
tool-side adapters over AuthoredDocumentService, and model-facing error texts."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

from localization import set_locale
import pytest

import agents.tooling.document_tool_support as support
import agents.tooling.document_tools as tools
from core.exceptions.authored_documents import (
    AttachmentReferenceError,
    DiagramBlockDiagnostic,
    DiagramValidationError,
    DocumentNotFoundError,
    EditApplicationError,
    EditDiagnostic,
    InvalidDocumentContentError,
    NoChangeError,
    RevisionConflictError,
    UnsupportedFormatChangeError,
)
from core.types.authored_documents import AuthorType, BlockChange, GenerationPhase

DOC_ID = uuid4()
CONFIG = {"configurable": {"user_id": "u1", "thread_id": str(uuid4()), "active_document": {"document_id": str(DOC_ID)}}}


class FakeService:
    def __init__(self, documents=(), revision=None, edit_exc=None):
        self.documents, self.revision, self.edit_exc = list(documents), revision, edit_exc
        self.revision_requests: list[int] = []

    async def list_for_thread(self, user_id, thread_id):
        return self.documents

    async def get_revision(self, user_id, document_id, revision_no):
        self.revision_requests.append(revision_no)
        return self.revision

    async def get_document(self, user_id, document_id):
        return self.documents[0]


@pytest.fixture(autouse=True)
def _offline_file_storage(monkeypatch) -> None:
    """Rendered files stay in the in-memory cache: no MinIO, no ``document`` row."""
    from service.storage.file_service import _STORE

    class _NoopDocumentRepository:
        async def create(self, **kwargs):
            return {}

    monkeypatch.setattr("service.storage.minio_service.upload_file", lambda **kwargs: "object-key")
    monkeypatch.setattr("infrastructure.db.repositories.document_repo.DocumentRepository", _NoopDocumentRepository)
    yield
    _STORE.clear()


@pytest.fixture
def events(monkeypatch) -> list[dict[str, Any]]:
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(support, "_emit_stream_event", captured.append)
    return captured


# ---------------------------------------------------------------------------
# list_documents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_documents_marks_the_active_one_first(monkeypatch, make_document) -> None:
    other, active = make_document(), make_document(id=DOC_ID)
    monkeypatch.setattr(support, "get_authored_document_service", lambda: FakeService([other, active]))
    payload = json.loads(await tools.list_documents.ainvoke({}, CONFIG))
    assert payload["documents"][0]["document_id"] == str(DOC_ID)
    assert payload["documents"][0]["active"] is True


@pytest.mark.asyncio
async def test_list_documents_describes_each_document(monkeypatch, make_document) -> None:
    document = make_document(head_revision_no=3)
    monkeypatch.setattr(support, "get_authored_document_service", lambda: FakeService([document]))

    payload = json.loads(await tools.list_documents.ainvoke({}, CONFIG))

    assert payload == {
        "documents": [
            {
                "document_id": str(document.id),
                "title": "Rapor",
                "filename": "rapor.docx",
                "format": "docx",
                "kind": "document",
                "head_revision_no": 3,
                "updated_at": document.updated_at.isoformat(),
                "active": False,
            }
        ]
    }


@pytest.mark.asyncio
async def test_list_documents_without_a_thread_is_empty(monkeypatch, make_document) -> None:
    monkeypatch.setattr(support, "get_authored_document_service", lambda: FakeService([make_document()]))

    payload = json.loads(await tools.list_documents.ainvoke({}, {"configurable": {"user_id": "u1"}}))

    assert payload == {"documents": []}


# ---------------------------------------------------------------------------
# read_document
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_document_returns_numbered_range(monkeypatch, make_document, make_revision) -> None:
    revision = make_revision(content="# A\n\nsatır iki\nsatır üç\n")
    monkeypatch.setattr(support, "get_authored_document_service", lambda: FakeService([make_document(id=DOC_ID)], revision))
    payload = json.loads(
        await tools.read_document.ainvoke({"document_id": str(DOC_ID), "start_line": 3, "end_line": 4}, CONFIG)
    )
    assert payload["content"] == "   3 | satır iki\n   4 | satır üç"
    assert payload["outline"] == [{"line": 1, "level": 1, "text": "A"}]


@pytest.mark.asyncio
async def test_read_document_defaults_to_the_head_draft_in_full(monkeypatch, make_document, make_revision) -> None:
    revision = make_revision(document_id=DOC_ID, revision_no=2, content="# A\nb\n", options={"theme": "academic"})
    service = FakeService([make_document(id=DOC_ID, head_revision_no=2)], revision)
    monkeypatch.setattr(support, "get_authored_document_service", lambda: service)

    payload = json.loads(await tools.read_document.ainvoke({"document_id": str(DOC_ID)}, CONFIG))

    assert service.revision_requests == [2]
    assert payload == {
        "document_id": str(DOC_ID),
        "revision_no": 2,
        "head_revision_no": 2,
        "title": "Rapor",
        "filename": "rapor.docx",
        "format": "docx",
        "source_format": "markdown",
        "options": {"theme": "academic"},
        "outline": [{"line": 1, "level": 1, "text": "A"}],
        "total_lines": 2,
        "start_line": 1,
        "end_line": 2,
        "content": "   1 | # A\n   2 | b",
    }


@pytest.mark.asyncio
async def test_read_document_clamps_the_range_and_can_omit_numbers(monkeypatch, make_document, make_revision) -> None:
    revision = make_revision(content="a\nb\nc")
    monkeypatch.setattr(support, "get_authored_document_service", lambda: FakeService([make_document(id=DOC_ID)], revision))

    payload = json.loads(
        await tools.read_document.ainvoke(
            {"document_id": str(DOC_ID), "start_line": 0, "end_line": 99, "with_line_numbers": False}, CONFIG
        )
    )

    assert (payload["start_line"], payload["end_line"], payload["total_lines"]) == (1, 3, 3)
    assert payload["content"] == "a\nb\nc"


@pytest.mark.asyncio
async def test_read_document_reads_an_older_draft(monkeypatch, make_document, make_revision) -> None:
    service = FakeService([make_document(id=DOC_ID, head_revision_no=4)], make_revision(revision_no=2))
    monkeypatch.setattr(support, "get_authored_document_service", lambda: service)

    payload = json.loads(await tools.read_document.ainvoke({"document_id": str(DOC_ID), "revision_no": 2}, CONFIG))

    assert service.revision_requests == [2]
    assert (payload["revision_no"], payload["head_revision_no"]) == (2, 4)


@pytest.mark.asyncio
async def test_read_document_has_no_outline_for_structured_content(monkeypatch, make_document, make_revision) -> None:
    from core.types.authored_documents import SourceFormat

    revision = make_revision(source_format=SourceFormat.JSON, format="json", content='{\n  "a": "# no"\n}')
    monkeypatch.setattr(support, "get_authored_document_service", lambda: FakeService([make_document(id=DOC_ID)], revision))

    payload = json.loads(await tools.read_document.ainvoke({"document_id": str(DOC_ID)}, CONFIG))

    assert payload["outline"] == []


@pytest.mark.asyncio
async def test_read_document_reports_a_missing_or_malformed_id() -> None:
    missing = await tools.read_document.ainvoke({"document_id": str(uuid4())}, CONFIG)
    malformed = await tools.read_document.ainvoke({"document_id": "not-a-uuid"}, CONFIG)

    for text in (missing, malformed):
        assert text.startswith("Error:") and "list_documents" in text


def test_read_document_description_warns_about_the_line_prefix() -> None:
    assert "copy old_str without the `NNNN | ` prefix" in tools.read_document.description


# ---------------------------------------------------------------------------
# Adapters: actor, payload, progress
# ---------------------------------------------------------------------------


def test_actor_from_config_reads_identity_from_the_run() -> None:
    thread_id = uuid4()
    actor = tools.actor_from_config(
        {"run_id": "r-1", "configurable": {"user_id": "u7", "thread_id": str(thread_id), "_persona_id": 12}}
    )

    assert actor.user_id == "u7"
    assert actor.author_type is AuthorType.AGENT
    assert actor.author_id == "12"
    assert actor.thread_id == thread_id
    assert actor.run_id == "r-1"


def test_actor_from_config_falls_back_safely() -> None:
    actor = tools.actor_from_config(
        {"configurable": {"user_id": "u7", "thread_id": "not-a-uuid", "agent_id": "writer"}}
    )

    assert (actor.user_id, actor.author_id, actor.thread_id, actor.run_id) == ("u7", "writer", None, None)
    assert tools.actor_from_config({"configurable": {"user_id": "u7"}}).author_id == "agent"


def test_actor_from_config_refuses_a_run_without_a_user() -> None:
    with pytest.raises(support.MissingUserError):
        tools.actor_from_config({})


def test_revision_payload_extends_the_generated_file_fields(make_result) -> None:
    result = make_result(revision_no=3, operation="edit")

    payload = tools.revision_payload(result)

    assert payload == {
        "__generated_file__": True,
        "file_id": "f9",
        "filename": "rapor.docx",
        "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "size_bytes": 10,
        "download_url": "/api/chat/file/f9?download=1",
        "document_id": str(result.document.id),
        "revision_no": 3,
        "revision_count": 3,
        "operation": "edit",
        "summary": "",
        "stats": {"added": 1, "removed": 1, "changes": []},
        "diagram_check": "passed",
    }
    json.dumps(payload)


def test_stream_progress_sink_emits_the_live_packet_contract(events) -> None:
    sink = tools.StreamProgressSink("edit_document", "edit", "rapor.docx", "docx", "d-1")

    sink.phase(GenerationPhase.APPLYING, applied=1, total=2, changes=(BlockChange("heading", "Giriş", "modified"),))

    assert events == [
        {
            "type": "document_generation_progress",
            "tool_name": "edit_document",
            "operation": "edit",
            "document_id": "d-1",
            "filename": "rapor.docx",
            "format": "docx",
            "phase": "applying",
            "applied": 1,
            "total": 2,
            "changes": [{"kind": "heading", "label": "Giriş", "change": "modified"}],
        }
    ]


@pytest.mark.asyncio
async def test_create_publishes_the_same_payload_it_returns(events, authored_document_repository) -> None:
    result = json.loads(
        await tools.create_document.ainvoke({"filename": "rapor", "format": "md", "content": "# Başlık"}, CONFIG)
    )

    (document,) = authored_document_repository.documents.values()
    assert result["document_id"] == str(document.id)
    assert (result["revision_no"], result["revision_count"], result["operation"]) == (1, 1, "create")
    assert str(document.thread_id) == CONFIG["configurable"]["thread_id"]

    phases = [e["phase"] for e in events if e["type"] == "document_generation_progress"]
    assert phases == ["rendering", "validating", "rendering"]
    lifecycle = [e for e in events if e["type"] != "generated_file"]
    assert all(e["tool_name"] == "create_document" and e["operation"] == "create" for e in lifecycle)
    generated = next(e for e in events if e["type"] == "generated_file")
    assert {k: v for k, v in generated.items() if k != "type"} == {
        k: v for k, v in result.items() if k != "__generated_file__"
    }
    assert events[-1]["type"] == "document_generation_end"
    assert events[-1]["status"] == "success"
    assert events[-1]["document_id"] == str(document.id)


@pytest.mark.asyncio
async def test_create_failure_closes_the_generation_with_an_english_error(events) -> None:
    set_locale("tr")
    try:
        text = await tools.create_document.ainvoke({"filename": "veri", "format": "json", "content": "{bad"}, CONFIG)
    finally:
        set_locale("en")

    assert text.startswith("Error: invalid content: invalid JSON")
    assert events[-1]["type"] == "document_generation_end"
    assert events[-1]["status"] == "error"
    assert events[-1]["error"] == text


@pytest.mark.asyncio
async def test_create_spreadsheet_goes_through_the_draft_service(events, authored_document_repository) -> None:
    sheets = [{"name": "Q1", "rows": [["a", "b"]]}]

    result = json.loads(
        await tools.create_spreadsheet.ainvoke({"filename": "satis", "format": "csv", "sheets": sheets}, CONFIG)
    )

    revision = authored_document_repository.revisions[(UUID(result["document_id"]), 1)]
    assert json.loads(revision.content) == sheets
    assert revision.summary == "created satis.csv"


# ---------------------------------------------------------------------------
# describe_error
# ---------------------------------------------------------------------------


def test_error_messages_are_actionable() -> None:
    conflict = RevisionConflictError(document_id=DOC_ID, base_revision_no=2, head_revision_no=3)
    text = tools.describe_error("edit_document", conflict)
    assert "draft 3" in text and "read_document" in text
    failed = EditApplicationError((EditDiagnostic(1, "not_found", 0, "| Finans onayı |"),))
    text = tools.describe_error("edit_document", failed)
    assert "edit 2" in text and "| Finans onayı |" in text and "nothing was saved" in text.lower()


def test_ambiguous_edit_message_does_not_nudge_towards_replace_all_inserts() -> None:
    ambiguous = tools.describe_error("edit_document", EditApplicationError((EditDiagnostic(0, "ambiguous", 3, None),)))
    inserting = tools.describe_error(
        "edit_document", EditApplicationError((EditDiagnostic(0, "replace_all_insert", 10, None),))
    )

    assert "add surrounding text" in ambiguous and "never for inserting" in ambiguous
    assert "matches 10 places" in inserting and "at every match" in inserting


def test_error_messages_cover_every_domain_error() -> None:
    ambiguous = EditApplicationError((EditDiagnostic(0, "ambiguous", 3, None),))
    diagram = DiagramValidationError((DiagramBlockDiagnostic(0, 12, 2, "Parse error"),))

    assert "matches 3 places" in tools.describe_error("edit_document", ambiguous)
    assert "diagram 1 (document line 12): Parse error" in tools.describe_error("edit_document", diagram)
    assert "does not modify" in tools.describe_error("edit_document", NoChangeError())
    assert "rewrite_document" in tools.describe_error("edit_document", UnsupportedFormatChangeError("docx", "json"))
    assert "list_documents" in tools.describe_error("read_document", DocumentNotFoundError(DOC_ID))
    attachment = tools.describe_error("edit_document", AttachmentReferenceError(("f1", "f2")))
    assert "f1, f2" in attachment
    assert "list_attachments" in attachment


def test_format_change_error_same_kind_points_to_rewrite_document() -> None:
    text = tools.describe_error("edit_document", UnsupportedFormatChangeError("pdf", "json"))

    assert "rewrite_document" in text
    assert "pdf" in text and "json" in text
    assert "can't be converted" not in text


def test_format_change_error_cross_kind_says_impossible() -> None:
    text = tools.describe_error("edit_document", UnsupportedFormatChangeError("docx", "xlsx"))

    assert "can't be converted" in text
    assert "Tell the user" in text
    assert "rewrite_document" not in text


def test_error_messages_stay_english_under_a_turkish_locale() -> None:
    """Domain errors translate their message per request locale; the model must
    still get English text built from the structured attributes."""
    set_locale("tr")
    try:
        invalid = InvalidDocumentContentError("content must not be empty")
        conflict = RevisionConflictError(document_id=DOC_ID, base_revision_no=1, head_revision_no=2)
        assert invalid.message.startswith("Geçersiz")
        invalid_text = tools.describe_error("create_document", invalid)
        conflict_text = tools.describe_error("edit_document", conflict)
    finally:
        set_locale("en")

    assert invalid_text == "Error: invalid content: content must not be empty"
    assert conflict_text.startswith("Error: the document changed since draft 1")


# ---------------------------------------------------------------------------
# get_document_tools
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rich", [True, False])
def test_get_document_tools_includes_the_workspace_tools(monkeypatch, rich) -> None:
    monkeypatch.setenv("DOCUMENT_TOOLS_ENABLED", str(True))
    monkeypatch.setenv("DOCUMENT_TOOLS_RICH_OPTIONS", str(rich))

    by_name = {t.name: t for t in tools.get_document_tools()}

    assert list(by_name) == [
        "create_document",
        "create_spreadsheet",
        "list_documents",
        "list_attachments",
        "read_document",
        "edit_document",
        "rewrite_document",
    ]
    if not rich:
        assert len(by_name["read_document"].description) < len(tools.read_document.description)
        assert len(by_name["list_documents"].description) < len(tools.list_documents.description)
