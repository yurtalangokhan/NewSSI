"""Tests for the ?download=1 attachment variant of GET /api/chat/file/{file_id}."""

from __future__ import annotations

from error_contract import DependencyUnavailableError
from fastapi import HTTPException
import pytest

from api.routes.file_route import get_chat_file
from service.auth.auth_service import AuthenticatedUser
from service.storage.file_service import store_file

USER = AuthenticatedUser(user_id="user-1", email="user@example.com")


@pytest.fixture(autouse=True)
def _clear_file_store():
    from service.storage.file_service import _STORE

    _STORE.clear()
    yield
    _STORE.clear()


@pytest.mark.asyncio
async def test_default_request_serves_inline_disposition():
    record = store_file("file-1", b"hello", "text/plain", "notes.txt", owner_id=USER.user_id)

    response = await get_chat_file(record.file_id, user=USER)

    assert response.headers["Content-Disposition"].startswith("inline")
    assert response.body == b"hello"


@pytest.mark.asyncio
async def test_response_carries_the_hardened_presentation_headers():
    """Spec T1: nosniff and a sandboxed CSP are the presentation-side half
    of the upload MIME allow-list defence -- see FileService.validate_upload."""
    record = store_file("file-hardened", b"hello", "text/plain", "notes.txt", owner_id=USER.user_id)

    response = await get_chat_file(record.file_id, user=USER)

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Content-Security-Policy"] == "sandbox; default-src 'none'"


@pytest.mark.asyncio
async def test_filename_quote_and_crlf_are_stripped_from_the_disposition_header():
    """A filename containing '"' or CR/LF must not be able to break out of
    the quoted Content-Disposition value or inject additional headers."""
    record = store_file(
        "file-injected",
        b"hello",
        "text/plain",
        'evil".pdf\r\nX-Injected: 1',
        owner_id=USER.user_id,
    )

    response = await get_chat_file(record.file_id, user=USER)

    disposition = response.headers["Content-Disposition"]
    assert "\r" not in disposition
    assert "\n" not in disposition
    assert "X-Injected" not in response.headers


@pytest.mark.asyncio
async def test_download_request_serves_attachment_disposition_with_original_bytes():
    record = store_file("file-2", b"hello", "text/plain", "notes.txt", owner_id=USER.user_id)

    response = await get_chat_file(record.file_id, download=True, user=USER)

    assert response.headers["Content-Disposition"].startswith("attachment")
    assert 'filename="notes.txt"' in response.headers["Content-Disposition"]
    assert response.body == b"hello"
    assert response.media_type == "text/plain"


@pytest.mark.asyncio
async def test_default_request_converts_xlsx_to_csv():
    import io

    import openpyxl

    wb = openpyxl.Workbook()
    wb.active.append(["a", "b"])
    buf = io.BytesIO()
    wb.save(buf)
    xlsx_bytes = buf.getvalue()

    record = store_file(
        "file-3",
        xlsx_bytes,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "satis.xlsx",
        owner_id=USER.user_id,
    )

    response = await get_chat_file(record.file_id, user=USER)

    assert response.media_type == "text/csv"
    assert response.body.decode("utf-8").strip() == "a,b"


@pytest.mark.asyncio
async def test_download_request_does_not_convert_xlsx_to_csv():
    import io

    import openpyxl

    wb = openpyxl.Workbook()
    wb.active.append(["a", "b"])
    buf = io.BytesIO()
    wb.save(buf)
    xlsx_bytes = buf.getvalue()

    record = store_file(
        "file-4",
        xlsx_bytes,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "satis.xlsx",
        owner_id=USER.user_id,
    )

    response = await get_chat_file(record.file_id, download=True, user=USER)

    assert (
        response.media_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert response.body == xlsx_bytes
    assert 'filename="satis.xlsx"' in response.headers["Content-Disposition"]


# ---------------------------------------------------------------------------
# Missing file — the 404 must never be cached by the browser. Without an
# explicit no-store, a single transient failure (e.g. a MinIO hiccup while the
# service warms its in-memory cache) gets cached by the browser as a 404 and
# every later preview attempt for that file_id fails from disk cache without
# ever hitting the backend again, even after the file becomes available.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_file_404_is_not_cacheable(monkeypatch):
    class _EmptyRepo:
        async def get_by_file_id(self, file_id, user_id):
            return None

    monkeypatch.setattr(
        "infrastructure.db.repositories.document_repo.DocumentRepository", _EmptyRepo
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_chat_file("does-not-exist", user=USER)

    assert exc_info.value.status_code == 404
    assert exc_info.value.headers is not None
    assert exc_info.value.headers.get("Cache-Control") == "no-store"


@pytest.mark.asyncio
async def test_minio_failure_is_dependency_unavailable(monkeypatch):
    class _RepoWithDoc:
        async def get_by_file_id(self, file_id, user_id):
            return {
                "minio_object_key": "documents/user-1/does-not-exist/file.txt",
                "mime_type": "text/plain",
                "filename": "file.txt",
            }

    def _boom(object_key):
        raise ConnectionError("minio unreachable")

    monkeypatch.setattr(
        "infrastructure.db.repositories.document_repo.DocumentRepository", _RepoWithDoc
    )
    monkeypatch.setattr("service.storage.minio_service.download_file", _boom)

    with pytest.raises(DependencyUnavailableError) as exc_info:
        await get_chat_file("some-file-id", user=USER)

    assert exc_info.value.status_code == 503
