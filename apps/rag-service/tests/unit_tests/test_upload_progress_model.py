from langconnect.models.documents import UploadProgress, UploadStatus


def test_progress_percent_is_zero_when_total_chunks_unknown() -> None:
    progress = UploadProgress(
        collection_id="c1",
        status=UploadStatus.PENDING,
        total_files=2,
        processed_files=0,
    )

    assert progress.progress_percent == 0.0


def test_progress_percent_based_on_chunks_when_known() -> None:
    progress = UploadProgress(
        collection_id="c1",
        status=UploadStatus.PROCESSING,
        total_files=1,
        processed_files=0,
        total_chunks=40,
        processed_chunks=10,
    )

    assert progress.progress_percent == 25.0


def test_progress_percent_full_when_completed() -> None:
    progress = UploadProgress(
        collection_id="c1",
        status=UploadStatus.COMPLETED,
        total_files=2,
        processed_files=2,
        total_chunks=10,
        processed_chunks=10,
    )

    assert progress.progress_percent == 100.0
