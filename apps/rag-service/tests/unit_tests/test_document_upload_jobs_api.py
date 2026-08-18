from langconnect.models.documents import UploadProgress, UploadStatus
from langconnect.services import document_upload_service
from tests.unit_tests.fixtures import get_async_test_client

USER_1_HEADERS = {
    "Authorization": "Bearer user1",
}


async def _create_collection(client, name: str) -> str:
    resp = await client.post(
        "/api/v1/collections",
        json={"name": name, "metadata": {}},
        headers=USER_1_HEADERS,
    )
    assert resp.status_code == 201
    return resp.json()["uuid"]


async def test_status_is_null_before_any_upload_job_started() -> None:
    async with get_async_test_client() as client:
        collection_id = await _create_collection(client, "upload_jobs_never_started")

        status_resp = await client.get(
            f"/api/v1/collections/{collection_id}/documents/upload-jobs/status",
            headers=USER_1_HEADERS,
        )
        assert status_resp.status_code == 200
        assert status_resp.json() is None


async def test_start_upload_job_then_status_reports_completed_with_chunks() -> None:
    async with get_async_test_client() as client:
        collection_id = await _create_collection(client, "upload_jobs_completes")

        files = [("files", ("job.txt", b"Hello job world.", "text/plain"))]
        start_resp = await client.post(
            f"/api/v1/collections/{collection_id}/documents/upload-jobs",
            files=files,
            headers=USER_1_HEADERS,
        )
        assert start_resp.status_code == 202
        started = start_resp.json()
        assert started["collection_id"] == collection_id
        assert started["status"] in ("pending", "processing", "completed")

        status_resp = await client.get(
            f"/api/v1/collections/{collection_id}/documents/upload-jobs/status",
            headers=USER_1_HEADERS,
        )
        assert status_resp.status_code == 200
        progress = status_resp.json()
        assert progress["status"] == "completed"
        assert progress["total_files"] == 1
        assert progress["processed_files"] == 1
        assert len(progress["added_chunk_ids"]) > 0
        assert progress["duplicate_files"] == []
        assert progress["failed_files"] == []


async def test_start_upload_job_skips_filename_already_in_collection() -> None:
    async with get_async_test_client() as client:
        collection_id = await _create_collection(client, "upload_jobs_dedup")

        files = [("files", ("dup.txt", b"First upload.", "text/plain"))]
        first = await client.post(
            f"/api/v1/collections/{collection_id}/documents/upload-jobs",
            files=files,
            headers=USER_1_HEADERS,
        )
        assert first.status_code == 202

        files_again = [("files", ("dup.txt", b"Second upload.", "text/plain"))]
        second = await client.post(
            f"/api/v1/collections/{collection_id}/documents/upload-jobs",
            files=files_again,
            headers=USER_1_HEADERS,
        )
        assert second.status_code == 202

        status_resp = await client.get(
            f"/api/v1/collections/{collection_id}/documents/upload-jobs/status",
            headers=USER_1_HEADERS,
        )
        progress = status_resp.json()
        assert progress["status"] == "completed"
        assert progress["duplicate_files"] == ["dup.txt"]
        assert progress["added_chunk_ids"] == []


async def test_start_upload_job_skips_same_content_under_different_filename() -> None:
    async with get_async_test_client() as client:
        collection_id = await _create_collection(client, "upload_jobs_content_dedup")

        files = [("files", ("original.txt", b"Identical bytes.", "text/plain"))]
        first = await client.post(
            f"/api/v1/collections/{collection_id}/documents/upload-jobs",
            files=files,
            headers=USER_1_HEADERS,
        )
        assert first.status_code == 202

        renamed_files = [
            ("files", ("renamed_copy.txt", b"Identical bytes.", "text/plain"))
        ]
        second = await client.post(
            f"/api/v1/collections/{collection_id}/documents/upload-jobs",
            files=renamed_files,
            headers=USER_1_HEADERS,
        )
        assert second.status_code == 202

        status_resp = await client.get(
            f"/api/v1/collections/{collection_id}/documents/upload-jobs/status",
            headers=USER_1_HEADERS,
        )
        progress = status_resp.json()
        assert progress["status"] == "completed"
        assert progress["duplicate_files"] == ["renamed_copy.txt"]
        assert progress["added_chunk_ids"] == []


async def test_start_upload_job_returns_existing_progress_when_already_active(
    monkeypatch,
) -> None:
    async with get_async_test_client() as client:
        collection_id = await _create_collection(client, "upload_jobs_already_active")

        active_progress = UploadProgress(
            collection_id=collection_id,
            status=UploadStatus.PROCESSING,
            total_files=1,
        )
        monkeypatch.setattr(
            document_upload_service,
            "get_upload_progress",
            lambda cid: active_progress,
        )

        files = [("files", ("second.txt", b"Should not start.", "text/plain"))]
        resp = await client.post(
            f"/api/v1/collections/{collection_id}/documents/upload-jobs",
            files=files,
            headers=USER_1_HEADERS,
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "processing"


async def test_start_upload_job_blocked_while_graph_building(monkeypatch) -> None:
    async with get_async_test_client() as client:
        collection_id = await _create_collection(client, "upload_jobs_graph_locked")

        from langconnect.models.graph import BuildProgress

        def _fake_progress(_: str):
            return BuildProgress(collection_id=collection_id, status="building")

        monkeypatch.setattr(
            "langconnect.services.build_lock.get_build_progress",
            _fake_progress,
        )

        files = [("files", ("locked.txt", b"Locked.", "text/plain"))]
        resp = await client.post(
            f"/api/v1/collections/{collection_id}/documents/upload-jobs",
            files=files,
            headers=USER_1_HEADERS,
        )
        assert resp.status_code == 409
