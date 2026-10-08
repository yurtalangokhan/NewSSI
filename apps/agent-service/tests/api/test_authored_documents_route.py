"""Route-level tests for versioned document drafts (Tasks 17-18).

Route coroutines are called directly with a fake service, following
``tests/api/test_file_route_ownership.py``: error-to-HTTP mapping belongs to
the app's global ``error_contract`` handler, so these tests assert on the
domain exception rather than an HTTP status code.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from api.routes import authored_documents_route as route
from core.exceptions.authored_documents import DocumentNotFoundError, RevisionConflictError, UnsupportedFormatChangeError
from core.types.authored_documents import (
    AuthoredDocument,
    AuthorType,
    DiagramCheck,
    DocumentKind,
    Operation,
    Revision,
    RevisionResult,
    RevisionStats,
    RevisionSummary,
    SourceFormat,
    StoredFileRef,
)
from service.auth.auth_service import AuthenticatedUser
from service.authored_documents.formats import DOCUMENT_FORMATS, SPREADSHEET_FORMATS
from service.documents.rendering import RenderedDocument

USER = AuthenticatedUser(user_id="u1", email="u1@example.com")
NOW = datetime(2026, 9, 27, tzinfo=UTC)
DOC = AuthoredDocument(uuid4(), "u1", uuid4(), None, DocumentKind.DOCUMENT, "R", "r.docx", "docx", 2, NOW, NOW)
SUMMARY = dict(
    id=uuid4(), document_id=DOC.id, revision_no=2, operation=Operation.EDIT, author_type=AuthorType.AGENT,
    author_id="agent", summary="SLA", stats=RevisionStats(added=1, removed=1), format="docx",
    rendered_file_id="f2", created_at=NOW,
)
REVISION = Revision(**SUMMARY, source_format=SourceFormat.MARKDOWN, content="# R\n", options={}, title="R",
                    filename="r.docx", content_sha256="0" * 64)


class FakeService:
    async def get_document(self, user_id, document_id):
        if document_id != DOC.id:
            raise DocumentNotFoundError(document_id)
        return DOC

    async def list_revisions(self, user_id, document_id):
        return [RevisionSummary(**SUMMARY)]

    async def get_revision(self, user_id, document_id, revision_no):
        return REVISION

    async def list_for_thread(self, user_id, thread_id):
        return [DOC]

    async def find_by_rendered_file(self, user_id, file_id):
        return (DOC, RevisionSummary(**SUMMARY)) if file_id == "f2" else None


@pytest.mark.asyncio
async def test_detail_lists_revisions() -> None:
    body = await route.get_document(DOC.id, user=USER, service=FakeService())
    assert body.head_revision_no == 2 and body.revisions[0].stats.added == 1


@pytest.mark.asyncio
async def test_revision_returns_content() -> None:
    body = await route.get_revision(DOC.id, 2, user=USER, service=FakeService())
    assert body.content == "# R\n" and body.source_format == "markdown"


@pytest.mark.asyncio
async def test_unknown_document_raises_domain_not_found() -> None:
    with pytest.raises(DocumentNotFoundError):
        await route.get_document(uuid4(), user=USER, service=FakeService())


@pytest.mark.asyncio
async def test_by_file_resolves_and_legacy_file_is_not_found() -> None:
    ref = await route.get_document_by_file("f2", user=USER, service=FakeService())
    assert (ref.document_id, ref.revision_no, ref.head_revision_no) == (DOC.id, 2, 2)
    with pytest.raises(DocumentNotFoundError) as excinfo:
        await route.get_document_by_file("legacy", user=USER, service=FakeService())
    assert excinfo.value.details == {"file_id": "legacy"}


@pytest.mark.asyncio
async def test_list_for_thread() -> None:
    body = await route.list_documents(thread_id=DOC.thread_id, user=USER, service=FakeService())
    assert [d.document_id for d in body.documents] == [DOC.id]


class WritingService(FakeService):
    def __init__(self, exc: Exception | None = None):
        self.exc, self.calls = exc, []

    async def save_user_edit(self, actor, document_id, *, base_revision_no, content, summary=""):
        self.calls.append((actor, base_revision_no, content))
        if self.exc:
            raise self.exc
        return RevisionResult(DOC, REVISION, StoredFileRef("f3", "r.docx", "x", 1, "/api/chat/file/f3?download=1"), DiagramCheck.PASSED)

    async def restore(self, actor, document_id, *, revision_no, base_revision_no):
        self.calls.append((actor, revision_no, base_revision_no))
        return RevisionResult(DOC, REVISION, StoredFileRef("f4", "r.docx", "x", 1, "/d"), DiagramCheck.NOT_APPLICABLE)

    async def export(self, user_id, document_id, revision_no, format):
        if format == "xlsx":
            raise UnsupportedFormatChangeError("docx", "xlsx")
        return RenderedDocument(b"%PDF", "application/pdf", "r.pdf")


@pytest.mark.asyncio
async def test_user_revision_is_saved_as_the_user() -> None:
    service = WritingService()
    body = await route.create_user_revision(
        DOC.id, route.UserRevisionRequest(base_revision_no=2, content="# R2"), user=USER, service=service
    )
    actor, base, content = service.calls[0]
    assert actor.author_type is AuthorType.USER and actor.user_id == "u1" and actor.thread_id == DOC.thread_id
    assert (base, content) == (2, "# R2") and body.file.file_id == "f3"


@pytest.mark.asyncio
async def test_conflict_propagates_with_head() -> None:
    service = WritingService(exc=RevisionConflictError(document_id=DOC.id, base_revision_no=1, head_revision_no=2))
    with pytest.raises(RevisionConflictError) as caught:
        await route.create_user_revision(
            DOC.id, route.UserRevisionRequest(base_revision_no=1, content="x"), user=USER, service=service
        )
    assert caught.value.details["head_revision_no"] == 2


@pytest.mark.asyncio
async def test_restore_passes_revision_and_base() -> None:
    service = WritingService()
    await route.restore_revision(DOC.id, 1, route.RestoreRequest(base_revision_no=2), user=USER, service=service)
    assert service.calls[0][1:] == (1, 2)


@pytest.mark.asyncio
async def test_export_streams_attachment_and_rejects_cross_kind() -> None:
    response = await route.export_revision(DOC.id, 2, format="pdf", user=USER, service=WritingService())
    assert response.body == b"%PDF"
    assert response.headers["content-disposition"].startswith("attachment")
    with pytest.raises(UnsupportedFormatChangeError):
        await route.export_revision(DOC.id, 2, format="xlsx", user=USER, service=WritingService())


def test_export_format_matches_known_formats() -> None:
    """``route.ExportFormat`` is spelled out by hand (mypy cannot unpack an
    arbitrary tuple into ``Literal[...]``); this keeps it in sync with the
    service's actual format catalog."""
    assert set(route.ExportFormat.__args__) == set(DOCUMENT_FORMATS) | set(SPREADSHEET_FORMATS)


def _client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.dependencies import require_user

    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[require_user] = lambda: USER
    app.dependency_overrides[route.get_service] = lambda: FakeService()
    return TestClient(app)


@pytest.mark.parametrize("bad", [0, 2_147_483_648])
def test_out_of_range_revision_numbers_are_a_422_not_a_500(bad: int) -> None:
    client = _client()
    base = f"/api/documents/{DOC.id}/revisions"
    assert client.get(f"{base}/{bad}").status_code == 422
    assert client.get(f"{base}/{bad}/export", params={"format": "pdf"}).status_code == 422
    assert client.post(f"{base}/{bad}/restore", json={"base_revision_no": 1}).status_code == 422
    assert client.post(f"{base}/1/restore", json={"base_revision_no": bad}).status_code == 422
    assert client.post(base, json={"base_revision_no": bad, "content": "x"}).status_code == 422


def test_user_revision_body_is_bounded() -> None:
    from core.types.authored_documents import MAX_DOCUMENT_CONTENT_CHARS, MAX_REVISION_SUMMARY_CHARS

    client = _client()
    url = f"/api/documents/{DOC.id}/revisions"
    long_content = {"base_revision_no": 2, "content": "x" * (MAX_DOCUMENT_CONTENT_CHARS + 1)}
    long_summary = {"base_revision_no": 2, "content": "x", "summary": "s" * (MAX_REVISION_SUMMARY_CHARS + 1)}
    assert client.post(url, json=long_content).status_code == 422
    assert client.post(url, json=long_summary).status_code == 422
