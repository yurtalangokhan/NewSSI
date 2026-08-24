import hashlib

import pytest

from langconnect.models.documents import UploadStatus
from langconnect.services import document_upload_service as svc


class FakeFile:
    """Minimal UploadFile double exposing `.filename` and async read/seek."""

    def __init__(self, filename: str, content: bytes | None = None) -> None:
        """Store the filename and readable content.

        Defaults content to something derived from the filename so distinct
        fake files never accidentally collide on content hash.
        """
        self.filename = filename
        self._content = content if content is not None else f"stub:{filename}".encode()

    async def read(self) -> bytes:
        """Return the seeded content."""
        return self._content

    async def seek(self, offset: int) -> None:
        """No-op seek — content is served from memory regardless of offset."""


class FakeDoc:
    """Stand-in for a LangChain Document; identity is all that matters here."""


class FakeCollection:
    """Minimal Collection double tracking upsert batch sizes."""

    def __init__(
        self,
        existing_filenames: set[str],
        existing_content_hashes: set[str] | None = None,
    ) -> None:
        """Seed the set of filenames/content hashes already in the collection."""
        self._existing_filenames = existing_filenames
        self._existing_content_hashes = existing_content_hashes or set()
        self.upsert_calls: list[int] = []

    async def list_filenames(self) -> set[str]:
        """Return the seeded set of existing filenames."""
        return set(self._existing_filenames)

    async def list_content_hashes(self) -> set[str]:
        """Return the seeded set of existing content hashes."""
        return set(self._existing_content_hashes)

    async def upsert(self, documents: list) -> list[str]:
        """Record the batch size and return fake chunk ids."""
        self.upsert_calls.append(len(documents))
        batch_index = len(self.upsert_calls)
        return [f"id-{batch_index}-{i}" for i in range(len(documents))]


@pytest.mark.asyncio
async def test_initialize_upload_progress_registers_pending():
    svc._upload_progress.clear()

    progress = svc.initialize_upload_progress("col-1", total_files=1)

    assert progress.status == UploadStatus.PENDING
    assert progress.total_files == 1
    assert svc.get_upload_progress("col-1") is progress


@pytest.mark.asyncio
async def test_get_upload_progress_returns_none_when_never_started():
    svc._upload_progress.clear()

    assert svc.get_upload_progress("never-started") is None


@pytest.mark.asyncio
async def test_run_upload_job_completes_and_embeds_documents(monkeypatch):
    svc._upload_progress.clear()
    collection = FakeCollection(existing_filenames=set())
    monkeypatch.setattr(svc, "Collection", lambda collection_id, user_id: collection)

    async def fake_process_document(file, metadata=None):
        return [FakeDoc(), FakeDoc(), FakeDoc()]

    monkeypatch.setattr(svc, "process_document", fake_process_document)

    files = [FakeFile("a.txt")]
    svc.initialize_upload_progress("col-1", total_files=1)

    await svc.run_upload_job("col-1", "user-1", files, [None])

    progress = svc.get_upload_progress("col-1")
    assert progress.status == UploadStatus.COMPLETED
    assert progress.processed_files == 1
    assert progress.total_chunks == 3
    assert progress.processed_chunks == 3
    assert len(progress.added_chunk_ids) == 3
    assert progress.duplicate_files == []


@pytest.mark.asyncio
async def test_run_upload_job_stamps_filename_into_metadata_even_without_caller_metadata(
    monkeypatch,
):
    """Dedup relies on metadata["filename"]; it must be set regardless of caller input."""
    svc._upload_progress.clear()
    collection = FakeCollection(existing_filenames=set())
    monkeypatch.setattr(svc, "Collection", lambda collection_id, user_id: collection)

    captured_metadata = {}

    async def fake_process_document(file, metadata=None):
        captured_metadata["value"] = metadata
        return [FakeDoc()]

    monkeypatch.setattr(svc, "process_document", fake_process_document)

    files = [FakeFile("a.txt")]
    svc.initialize_upload_progress("col-1", total_files=1)

    await svc.run_upload_job("col-1", "user-1", files, [None])

    assert captured_metadata["value"]["filename"] == "a.txt"


@pytest.mark.asyncio
async def test_run_upload_job_stamps_content_hash_into_metadata(monkeypatch):
    svc._upload_progress.clear()
    collection = FakeCollection(existing_filenames=set())
    monkeypatch.setattr(svc, "Collection", lambda collection_id, user_id: collection)

    captured_metadata = {}

    async def fake_process_document(file, metadata=None):
        captured_metadata["value"] = metadata
        return [FakeDoc()]

    monkeypatch.setattr(svc, "process_document", fake_process_document)

    files = [FakeFile("a.txt", content=b"hello world")]
    svc.initialize_upload_progress("col-1", total_files=1)

    await svc.run_upload_job("col-1", "user-1", files, [None])

    expected_hash = hashlib.sha256(b"hello world").hexdigest()
    assert captured_metadata["value"]["content_hash"] == expected_hash


@pytest.mark.asyncio
async def test_run_upload_job_skips_file_with_content_hash_already_in_collection(
    monkeypatch,
):
    """Same content under a different filename is still a duplicate."""
    svc._upload_progress.clear()
    existing_hash = hashlib.sha256(b"identical bytes").hexdigest()
    collection = FakeCollection(
        existing_filenames=set(), existing_content_hashes={existing_hash}
    )
    monkeypatch.setattr(svc, "Collection", lambda collection_id, user_id: collection)

    async def fake_process_document(file, metadata=None):
        raise AssertionError("Should not process a content-duplicate file")

    monkeypatch.setattr(svc, "process_document", fake_process_document)

    files = [FakeFile("renamed.txt", content=b"identical bytes")]
    svc.initialize_upload_progress("col-1", total_files=1)

    await svc.run_upload_job("col-1", "user-1", files, [None])

    progress = svc.get_upload_progress("col-1")
    assert progress.duplicate_files == ["renamed.txt"]
    assert progress.added_chunk_ids == []


@pytest.mark.asyncio
async def test_run_upload_job_skips_content_duplicate_within_same_batch(monkeypatch):
    svc._upload_progress.clear()
    collection = FakeCollection(existing_filenames=set())
    monkeypatch.setattr(svc, "Collection", lambda collection_id, user_id: collection)

    call_count = {"n": 0}

    async def fake_process_document(file, metadata=None):
        call_count["n"] += 1
        return [FakeDoc()]

    monkeypatch.setattr(svc, "process_document", fake_process_document)

    files = [
        FakeFile("first.txt", content=b"same bytes"),
        FakeFile("second.txt", content=b"same bytes"),
    ]
    svc.initialize_upload_progress("col-1", total_files=2)

    await svc.run_upload_job("col-1", "user-1", files, [None, None])

    progress = svc.get_upload_progress("col-1")
    assert call_count["n"] == 1
    assert progress.duplicate_files == ["second.txt"]


@pytest.mark.asyncio
async def test_run_upload_job_skips_filename_already_in_collection(monkeypatch):
    svc._upload_progress.clear()
    collection = FakeCollection(existing_filenames={"dup.txt"})
    monkeypatch.setattr(svc, "Collection", lambda collection_id, user_id: collection)

    async def fake_process_document(file, metadata=None):
        raise AssertionError("Should not process a duplicate file")

    monkeypatch.setattr(svc, "process_document", fake_process_document)

    files = [FakeFile("dup.txt")]
    svc.initialize_upload_progress("col-1", total_files=1)

    await svc.run_upload_job("col-1", "user-1", files, [None])

    progress = svc.get_upload_progress("col-1")
    assert progress.status == UploadStatus.COMPLETED
    assert progress.duplicate_files == ["dup.txt"]
    assert progress.added_chunk_ids == []


@pytest.mark.asyncio
async def test_run_upload_job_skips_duplicate_within_same_batch(monkeypatch):
    svc._upload_progress.clear()
    collection = FakeCollection(existing_filenames=set())
    monkeypatch.setattr(svc, "Collection", lambda collection_id, user_id: collection)

    call_count = {"n": 0}

    async def fake_process_document(file, metadata=None):
        call_count["n"] += 1
        return [FakeDoc()]

    monkeypatch.setattr(svc, "process_document", fake_process_document)

    files = [FakeFile("same.txt"), FakeFile("same.txt")]
    svc.initialize_upload_progress("col-1", total_files=2)

    await svc.run_upload_job("col-1", "user-1", files, [None, None])

    progress = svc.get_upload_progress("col-1")
    assert call_count["n"] == 1
    assert progress.duplicate_files == ["same.txt"]
    assert progress.processed_files == 2


@pytest.mark.asyncio
async def test_run_upload_job_continues_after_file_processing_error(monkeypatch):
    svc._upload_progress.clear()
    collection = FakeCollection(existing_filenames=set())
    monkeypatch.setattr(svc, "Collection", lambda collection_id, user_id: collection)

    async def fake_process_document(file, metadata=None):
        if file.filename == "bad.txt":
            raise ValueError("boom")
        return [FakeDoc()]

    monkeypatch.setattr(svc, "process_document", fake_process_document)

    files = [FakeFile("bad.txt"), FakeFile("good.txt")]
    svc.initialize_upload_progress("col-1", total_files=2)

    await svc.run_upload_job("col-1", "user-1", files, [None, None])

    progress = svc.get_upload_progress("col-1")
    assert progress.status == UploadStatus.COMPLETED
    assert progress.failed_files == ["bad.txt"]
    assert progress.processed_files == 2
    assert len(progress.added_chunk_ids) == 1


@pytest.mark.asyncio
async def test_run_upload_job_embeds_in_batches_for_progress(monkeypatch):
    svc._upload_progress.clear()
    collection = FakeCollection(existing_filenames=set())
    monkeypatch.setattr(svc, "Collection", lambda collection_id, user_id: collection)
    monkeypatch.setattr(svc, "UPLOAD_EMBED_BATCH_SIZE", 2)

    async def fake_process_document(file, metadata=None):
        return [FakeDoc() for _ in range(5)]

    monkeypatch.setattr(svc, "process_document", fake_process_document)

    files = [FakeFile("big.txt")]
    svc.initialize_upload_progress("col-1", total_files=1)

    await svc.run_upload_job("col-1", "user-1", files, [None])

    progress = svc.get_upload_progress("col-1")
    assert collection.upsert_calls == [2, 2, 1]
    assert progress.processed_chunks == 5
