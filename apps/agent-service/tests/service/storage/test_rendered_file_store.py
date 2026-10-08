"""Tests for RenderedFileStore, the save/delete persistence extracted from
``agents.tooling.document_tools._persist_generated_file``."""

from __future__ import annotations

import pytest

from service.storage import file_service
from service.storage.rendered_file_store import RenderedFileStore


@pytest.mark.asyncio
async def test_save_caches_and_records_best_effort(monkeypatch) -> None:
    recorded: dict = {}
    monkeypatch.setattr("service.storage.minio_service.upload_file", lambda **kw: "documents/u/f/x.pdf")

    async def fake_persist(**kwargs):
        recorded.update(kwargs)

    monkeypatch.setattr(file_service, "persist_document_record", fake_persist)
    stored = await RenderedFileStore().save(
        data=b"%PDF", filename="x.pdf", mime_type="application/pdf", user_id="u", thread_id=None
    )
    assert file_service.get_file(stored.file_id).data == b"%PDF"
    assert recorded["minio_object_key"] == "documents/u/f/x.pdf"
    assert stored.download_url == f"/api/chat/file/{stored.file_id}?download=1"


@pytest.mark.asyncio
async def test_save_survives_storage_failures(monkeypatch) -> None:
    def boom(**kw):
        raise RuntimeError("minio down")

    async def boom_db(**kw):
        raise RuntimeError("db down")

    monkeypatch.setattr("service.storage.minio_service.upload_file", boom)
    monkeypatch.setattr(file_service, "persist_document_record", boom_db)
    stored = await RenderedFileStore().save(
        data=b"x", filename="x.txt", mime_type="text/plain", user_id="u", thread_id=None
    )
    assert file_service.get_file(stored.file_id) is not None


@pytest.mark.asyncio
async def test_delete_evicts_cache_and_removes_owned_file(monkeypatch) -> None:
    calls: dict = {}

    class _FakeRepo:
        async def get_by_file_id(self, file_id, user_id):
            calls["get"] = (file_id, user_id)
            return {"minio_object_key": "documents/u/f/x.pdf"}

        async def delete_by_file_id(self, file_id):
            calls["delete_db"] = file_id
            return True

    monkeypatch.setattr("infrastructure.db.repositories.document_repo.DocumentRepository", _FakeRepo)
    monkeypatch.setattr("service.storage.minio_service.upload_file", lambda **kw: "documents/u/f/x.pdf")
    monkeypatch.setattr(
        "service.storage.minio_service.delete_file",
        lambda object_key: calls.setdefault("delete_minio", object_key),
    )

    async def fake_persist(**kwargs):
        pass

    monkeypatch.setattr(file_service, "persist_document_record", fake_persist)

    stored = await RenderedFileStore().save(
        data=b"%PDF", filename="x.pdf", mime_type="application/pdf", user_id="u", thread_id=None
    )
    await RenderedFileStore().delete(stored.file_id, "u")

    assert file_service.get_file(stored.file_id) is None
    assert calls["get"] == (stored.file_id, "u")
    assert calls["delete_db"] == stored.file_id
    assert calls["delete_minio"] == "documents/u/f/x.pdf"


@pytest.mark.asyncio
async def test_delete_does_not_remove_another_users_file(monkeypatch) -> None:
    calls: dict = {}

    class _FakeRepo:
        async def get_by_file_id(self, file_id, user_id):
            calls["get"] = (file_id, user_id)
            return None  # not owned by this user (or does not exist)

        async def delete_by_file_id(self, file_id):
            calls["delete_db"] = file_id
            return True

    monkeypatch.setattr("infrastructure.db.repositories.document_repo.DocumentRepository", _FakeRepo)

    async def fake_persist(**kwargs):
        pass

    monkeypatch.setattr(file_service, "persist_document_record", fake_persist)
    monkeypatch.setattr("service.storage.minio_service.upload_file", lambda **kw: "documents/u/f/x.pdf")

    stored = await RenderedFileStore().save(
        data=b"%PDF", filename="x.pdf", mime_type="application/pdf", user_id="u", thread_id=None
    )
    await RenderedFileStore().delete(stored.file_id, "someone-else")

    assert "delete_db" not in calls
    # The cache entry is still evicted: the caller only calls delete() for a
    # file it just saved, so cache cleanup does not depend on DB ownership.
    assert file_service.get_file(stored.file_id) is None
