"""Tests for the ?download=1 attachment variant of GET /api/chat/file/{file_id}."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from api.routes.FileRoute import get_chat_file
from service.FileService import store_file


@pytest.fixture(autouse=True)
def _clear_file_store():
    from service.FileService import _STORE

    _STORE.clear()
    yield
    _STORE.clear()


@pytest.mark.asyncio
async def test_default_request_serves_inline_disposition():
    record = store_file("file-1", b"hello", "text/plain", "notes.txt")

    response = await get_chat_file(record.file_id)

    assert response.headers["Content-Disposition"].startswith("inline")
    assert response.body == b"hello"


@pytest.mark.asyncio
async def test_download_request_serves_attachment_disposition_with_original_bytes():
    record = store_file("file-2", b"hello", "text/plain", "notes.txt")

    response = await get_chat_file(record.file_id, download=True)

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
    )

    response = await get_chat_file(record.file_id)

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
    )

    response = await get_chat_file(record.file_id, download=True)

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
        async def get_by_file_id(self, file_id):
            return None

    monkeypatch.setattr("core.db.repositories.document_repo.DocumentRepository", _EmptyRepo)

    with pytest.raises(HTTPException) as exc_info:
        await get_chat_file("does-not-exist")

    assert exc_info.value.status_code == 404
    assert exc_info.value.headers is not None
    assert exc_info.value.headers.get("Cache-Control") == "no-store"


@pytest.mark.asyncio
async def test_minio_failure_404_is_not_cacheable(monkeypatch):
    class _RepoWithDoc:
        async def get_by_file_id(self, file_id):
            return {
                "minio_object_key": "documents/user-1/does-not-exist/file.txt",
                "mime_type": "text/plain",
                "filename": "file.txt",
            }

    def _boom(object_key):
        raise ConnectionError("minio unreachable")

    monkeypatch.setattr("core.db.repositories.document_repo.DocumentRepository", _RepoWithDoc)
    monkeypatch.setattr("service.MinioService.download_file", _boom)

    with pytest.raises(HTTPException) as exc_info:
        await get_chat_file("some-file-id")

    assert exc_info.value.status_code == 404
    assert exc_info.value.headers is not None
    assert exc_info.value.headers.get("Cache-Control") == "no-store"
