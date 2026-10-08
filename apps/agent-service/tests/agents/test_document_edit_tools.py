"""Tests for edit_document / rewrite_document, edit-argument recovery, and the
failure-path guarantees shared with the create and read tools."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

import agents.tooling.document_create_tools as create_tools
import agents.tooling.document_tool_support as support
import agents.tooling.document_tools as tools
from core.exceptions.authored_documents import (
    DocumentNotFoundError,
    EditApplicationError,
    EditDiagnostic,
    RevisionConflictError,
)

DOC_ID = uuid4()
CONFIG = {"configurable": {"user_id": "u1", "thread_id": str(uuid4())}}


class RecordingService:
    def __init__(self, result=None, exc=None, head=None, lookup_exc=None):
        self.result, self.exc, self.head, self.lookup_exc, self.calls = result, exc, head, lookup_exc, []

    async def get_document(self, user_id, document_id):
        if self.lookup_exc:
            raise self.lookup_exc
        return self.head

    async def edit(self, actor, document_id, **kwargs):
        self.calls.append(("edit", document_id, kwargs))
        if self.exc:
            raise self.exc
        return self.result

    async def rewrite(self, actor, document_id, **kwargs):
        self.calls.append(("rewrite", document_id, kwargs))
        if self.exc:
            raise self.exc
        return self.result


@pytest.fixture
def emitted(monkeypatch):
    packets: list[dict] = []
    monkeypatch.setattr(support, "_emit_stream_event", packets.append)
    return packets


@pytest.fixture
def head(make_document):
    return make_document(id=DOC_ID, filename="rapor.md", format="md", head_revision_no=2)


def _use(monkeypatch, service) -> RecordingService:
    monkeypatch.setattr(support, "get_authored_document_service", lambda: service)
    return service


def _ends(packets: list[dict]) -> list[dict]:
    return [p for p in packets if p["type"] == "document_generation_end"]


@pytest.mark.asyncio
async def test_edit_document_passes_typed_edits_and_returns_revision_payload(
    monkeypatch, emitted, head, make_result
) -> None:
    service = _use(monkeypatch, RecordingService(result=make_result(revision_no=3, operation="edit"), head=head))
    payload = json.loads(
        await tools.edit_document.ainvoke(
            {
                "document_id": str(DOC_ID),
                "base_revision_no": 2,
                "summary": "SLA",
                "edits": [{"old_str": "2 iş günü", "new_str": "1 iş günü"}],
                "options": {"toc": None},
            },
            CONFIG,
        )
    )
    _, document_id, kwargs = service.calls[0]
    assert document_id == DOC_ID and kwargs["base_revision_no"] == 2
    assert kwargs["edits"][0].old_str == "2 iş günü"
    assert kwargs["options_patch"] == {"toc": None}
    assert payload["revision_no"] == 3 and payload["operation"] == "edit"
    assert [p["type"] for p in emitted][-2:] == ["generated_file", "document_generation_end"]
    started = emitted[0]
    assert started["type"] == "document_generation_progress"
    assert (started["operation"], started["tool_name"], started["document_id"]) == (
        "edit",
        "edit_document",
        str(DOC_ID),
    )
    assert (started["filename"], started["format"]) == ("rapor.md", "md")


@pytest.mark.asyncio
async def test_edit_failure_returns_instructions_and_closes_generation(monkeypatch, emitted, head) -> None:
    error = EditApplicationError((EditDiagnostic(0, "ambiguous", 2, None),))
    _use(monkeypatch, RecordingService(exc=error, head=head))
    text = await tools.edit_document.ainvoke(
        {"document_id": str(DOC_ID), "base_revision_no": 1, "summary": "x", "edits": [{"old_str": "a", "new_str": "b"}]},
        CONFIG,
    )
    assert text.startswith("Error:") and "matches 2 places" in text
    assert emitted[-1]["type"] == "document_generation_end" and emitted[-1]["status"] == "error"
    assert len(_ends(emitted)) == 1


@pytest.mark.asyncio
async def test_rewrite_document_passes_content_and_options(monkeypatch, emitted, head, make_result) -> None:
    service = _use(monkeypatch, RecordingService(result=make_result(revision_no=3, operation="rewrite"), head=head))
    payload = json.loads(
        await tools.rewrite_document.ainvoke(
            {"document_id": str(DOC_ID), "base_revision_no": 2, "summary": "baştan", "content": "# Yeni"},
            CONFIG,
        )
    )
    op, _, kwargs = service.calls[0]
    assert op == "rewrite" and kwargs["content"] == "# Yeni" and kwargs["options"] is None
    assert payload["operation"] == "rewrite"
    assert emitted[0]["operation"] == "rewrite" and emitted[0]["tool_name"] == "rewrite_document"


@pytest.mark.asyncio
async def test_rewrite_conflict_is_described(monkeypatch, emitted, head) -> None:
    _use(monkeypatch, RecordingService(exc=RevisionConflictError(document_id=DOC_ID, base_revision_no=1, head_revision_no=2), head=head))
    text = await tools.rewrite_document.ainvoke(
        {"document_id": str(DOC_ID), "base_revision_no": 1, "summary": "x", "content": "y"}, CONFIG
    )
    assert "latest is draft 2" in text
    assert len(_ends(emitted)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["edit_document", "rewrite_document"])
async def test_bad_document_id_is_not_found_and_opens_nothing(monkeypatch, emitted, tool_name) -> None:
    service = _use(monkeypatch, RecordingService())
    args = {"document_id": "not-a-uuid", "base_revision_no": 1, "summary": "x"}
    args |= {"edits": [{"old_str": "a", "new_str": "b"}]} if tool_name == "edit_document" else {"content": "y"}
    text = await getattr(tools, tool_name).ainvoke(args, CONFIG)
    assert text == tools.describe_error(tool_name, DocumentNotFoundError("not-a-uuid"))
    assert service.calls == [] and emitted == []


@pytest.mark.asyncio
async def test_unknown_document_lookup_is_described(monkeypatch, emitted) -> None:
    _use(monkeypatch, RecordingService(lookup_exc=DocumentNotFoundError(DOC_ID)))
    text = await tools.edit_document.ainvoke(
        {"document_id": str(DOC_ID), "base_revision_no": 1, "summary": "x", "edits": [{"old_str": "a", "new_str": "b"}]},
        CONFIG,
    )
    assert "list_documents" in text and emitted == []


@pytest.mark.asyncio
async def test_unexpected_edit_failure_returns_fixed_text(monkeypatch, emitted, head) -> None:
    _use(monkeypatch, RecordingService(exc=RuntimeError("postgres://secret@db"), head=head))
    text = await tools.edit_document.ainvoke(
        {"document_id": str(DOC_ID), "base_revision_no": 1, "summary": "x", "edits": [{"old_str": "a", "new_str": "b"}]},
        CONFIG,
    )
    assert text == "Error: edit_document failed unexpectedly; the error was logged."
    assert "secret" not in json.dumps(emitted)
    assert len(_ends(emitted)) == 1


# ---------------------------------------------------------------------------
# create path failure handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_sanitize_failure_emits_exactly_one_error_end(monkeypatch, emitted) -> None:
    def _boom(*args, **kwargs):
        raise RuntimeError("/var/secret/path")

    monkeypatch.setattr(create_tools.docgen, "sanitize_filename", _boom)
    text = await tools.create_document.ainvoke({"filename": "r", "format": "md", "content": "x"}, CONFIG)
    assert text == "Error: create_document failed unexpectedly; the error was logged."
    ends = _ends(emitted)
    assert len(ends) == 1 and ends[0]["status"] == "error"


@pytest.mark.asyncio
async def test_create_options_parse_failure_emits_exactly_one_error_end(monkeypatch, emitted) -> None:
    def _boom(*args, **kwargs):
        raise ValueError("bad")

    monkeypatch.setattr(create_tools.docgen, "parse_spreadsheet_options", _boom)
    text = await tools.create_spreadsheet.ainvoke(
        {"filename": "t", "format": "csv", "sheets": [{"name": "s", "rows": [["a"]]}]}, CONFIG
    )
    assert text.endswith("failed unexpectedly; the error was logged.")
    assert [e["status"] for e in _ends(emitted)] == ["error"]


@pytest.mark.asyncio
async def test_create_publish_failure_emits_one_error_end_and_no_success(monkeypatch, emitted) -> None:
    def _boom(*args, **kwargs):
        raise RuntimeError("packet")

    monkeypatch.setattr(support, "revision_payload", _boom)
    text = await tools.create_document.ainvoke({"filename": "r", "format": "md", "content": "# x"}, CONFIG)
    assert text == "Error: create_document failed unexpectedly; the error was logged."
    assert [e["status"] for e in _ends(emitted)] == ["error"]


# ---------------------------------------------------------------------------
# read/list generic failures and revision_no
# ---------------------------------------------------------------------------


class _BrokenService:
    async def list_for_thread(self, *args):
        raise RuntimeError("secret")

    async def get_document(self, *args):
        raise RuntimeError("secret")


@pytest.mark.asyncio
async def test_list_and_read_unexpected_failures_return_fixed_text(monkeypatch) -> None:
    _use(monkeypatch, _BrokenService())
    assert await tools.list_documents.ainvoke({}, CONFIG) == (
        "Error: list_documents failed unexpectedly; the error was logged."
    )
    assert await tools.read_document.ainvoke({"document_id": str(DOC_ID)}, CONFIG) == (
        "Error: read_document failed unexpectedly; the error was logged."
    )


class _HeadOnlyService:
    def __init__(self, head):
        self.head, self.revision_requests = head, []

    async def get_document(self, user_id, document_id):
        return self.head

    async def get_revision(self, user_id, document_id, revision_no):
        self.revision_requests.append(revision_no)
        raise AssertionError("must not be reached")


@pytest.mark.asyncio
@pytest.mark.parametrize("revision_no", [0, -1])
async def test_read_document_non_positive_revision_is_not_found(monkeypatch, head, revision_no) -> None:
    service = _use(monkeypatch, _HeadOnlyService(head))
    text = await tools.read_document.ainvoke({"document_id": str(DOC_ID), "revision_no": revision_no}, CONFIG)
    assert text.startswith("Error: that document or draft does not exist")
    assert service.revision_requests == []


def test_describe_error_generic_branch_does_not_leak_the_exception() -> None:
    assert tools.describe_error("x_tool", RuntimeError("secret")) == (
        "Error: x_tool failed unexpectedly; the error was logged."
    )


# ---------------------------------------------------------------------------
# argument recovery and tool list
# ---------------------------------------------------------------------------


def test_recover_edit_args_accepts_common_model_mistakes() -> None:
    assert tools.recover_edit_tool_args({"edits": '[{"old_str": "a", "new_str": "b"}]'})["edits"] == [
        {"old_str": "a", "new_str": "b"}
    ]
    assert tools.recover_edit_tool_args({"edits": {"old": "a", "new": "b"}})["edits"] == [
        {"old_str": "a", "new_str": "b"}
    ]
    assert tools.recover_edit_tool_args({"edits": [{"old_text": "a", "new_text": "b", "replace_all": True}]})[
        "edits"
    ] == [{"old_str": "a", "new_str": "b", "replace_all": True}]


def test_recover_edit_args_wraps_a_top_level_pair_and_leaves_bad_json() -> None:
    recovered = tools.recover_edit_tool_args({"document_id": "d", "old_str": "a", "new_str": "b"})
    assert recovered == {"document_id": "d", "edits": [{"old_str": "a", "new_str": "b"}]}
    assert tools.recover_edit_tool_args({"edits": "not json"}) == {"edits": "not json"}
    valid = {"edits": [{"old_str": "a", "new_str": "b"}]}
    assert tools.recover_edit_tool_args(valid) == valid


@pytest.mark.parametrize("rich", [True, False])
def test_get_document_tools_returns_every_tool(monkeypatch, rich) -> None:
    monkeypatch.setenv("DOCUMENT_TOOLS_ENABLED", str(True))
    monkeypatch.setenv("DOCUMENT_TOOLS_RICH_OPTIONS", str(rich))
    names = [t.name for t in tools.get_document_tools()]
    assert names == [
        "create_document",
        "create_spreadsheet",
        "list_documents",
        "list_attachments",
        "read_document",
        "edit_document",
        "rewrite_document",
    ]


def test_edit_docstring_carries_the_edit_rules() -> None:
    description = tools.edit_document.description
    for rule in ("verbatim", "exactly one place", "one edit per distinct change", "anchor", "latest base_revision_no"):
        assert rule in description
    assert "Never fall back to creating a new file" in description
    assert "set a key to null to reset it" in " ".join(description.split())
    assert "JSON sheets array" in tools.rewrite_document.description
