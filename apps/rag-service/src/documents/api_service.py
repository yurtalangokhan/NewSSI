# Copyright (c) 2026 Agentic AI Platform
"""Framework-independent document operations and upload orchestration."""

from collections.abc import Callable
from typing import Any

from error_contract import BadRequestError, DatabaseOperationError
from langchain_core.documents import Document
from localization import t
from pydantic import TypeAdapter, ValidationError

from src.collections.write_guards import (
    ensure_collection_mutable,
    ensure_not_connector_managed_collection,
)
from src.documents import upload_service as document_upload_service
from src.documents.processor import process_document
from src.documents.schemas import (
    FileUploadDTO,
    SearchQuery,
    SearchResult,
    UploadJobStartResponse,
    UploadProgress,
)
from src.documents.service import Collection
from src.documents.upload_limits import (
    _AsyncReadable,
    check_batch_size,
    read_files_within_total_limit,
)
from src.shared.observability import get_logger

_metadata_adapter = TypeAdapter(list[dict[str, Any]])
logger = get_logger(__name__)


async def documents_create(
    *,
    collection_id: str,
    user_id: str,
    files: list[_AsyncReadable],
    declared_content_length: str | None,
    metadatas_json: str | None,
) -> dict[str, Any]:
    """Processes and indexes (adds) new document files with optional metadata."""
    check_batch_size(file_count=len(files), declared_content_length=declared_content_length)
    await ensure_not_connector_managed_collection(str(collection_id))
    ensure_collection_mutable(str(collection_id))

    # If no metadata JSON is provided, fill with None
    if not metadatas_json:
        metadatas: list[dict] | list[None] = [None] * len(files)
    else:
        try:
            # This will both parse the JSON and check the Python types
            # (i.e. that it's a list, and every item is a dict)
            metadatas = _metadata_adapter.validate_json(metadatas_json)
        except ValidationError as e:
            raise BadRequestError(
                code="document.invalid_metadata",
                message_key="errors.rag.document.invalid_metadata",
                details={"errors": e.errors(include_context=False)},
            ) from e
        # Now just check that the list length matches
        if len(metadatas) != len(files):
            raise BadRequestError(
                code="document.metadata_count_mismatch",
                message_key="errors.rag.document.metadata_count_mismatch",
                message_params={
                    "metadata_count": len(metadatas),
                    "file_count": len(files),
                },
            )

    docs_to_index: list[Document] = []
    processed_files_count = 0
    failed_files = []

    # Convert UploadFile objects to framework-agnostic DTOs once, up-front,
    # so that all downstream code (services, processors) never sees FastAPI
    # types.
    file_dtos: list[FileUploadDTO] = await read_files_within_total_limit(files)

    # Pair files with their corresponding metadata
    for file_dto, metadata in zip(file_dtos, metadatas, strict=False):
        try:
            # Pass metadata to process_document
            langchain_docs = await process_document(file_dto, metadata=metadata)
            if langchain_docs:
                docs_to_index.extend(langchain_docs)
                processed_files_count += 1
            else:
                logger.info(f"Warning: File {file_dto.filename} resulted in no processable documents.")
                # Decide if this constitutes a failure
                # failed_files.append(file_dto.filename)

        except Exception as proc_exc:  # Preserve partial success for independent files.
            # Log the error and the file that caused it
            logger.info(f"Error processing file {file_dto.filename}: {proc_exc}")
            failed_files.append(file_dto.filename)
            # Decide on behavior: continue processing others or fail fast?
            # For now, let's collect failures and report them, but continue processing.
        finally:
            # Every file is fully processed (successfully or not) by this
            # point in this synchronous endpoint, so its temp file is no
            # longer needed -- unlike the async job below, nothing else
            # will read it later.
            file_dto.cleanup()

    # If after processing all files, none yielded documents, raise error
    if not docs_to_index:
        raise BadRequestError(
            code="document.no_documents_processed",
            message_key="errors.rag.document.no_documents_processed",
            details={"failed_files": failed_files},
        )

    # If some files failed but others succeeded, proceed with adding successful ones
    # but maybe inform the user about the failures.
    collection = Collection(
        collection_id=str(collection_id),
        user_id=user_id,
    )
    added_ids = await collection.upsert(docs_to_index)
    if not added_ids:
        # This might indicate a problem with the vector store itself
        raise DatabaseOperationError(
            code="document.vectorstore_add_failed",
            message_key="errors.rag.document.vectorstore_add_failed",
        )
    # Construct response message
    success_message = f"{len(added_ids)} document chunk(s) from {processed_files_count} file(s) added successfully."
    response_data = {
        "success": True,
        "message": success_message,
        "added_chunk_ids": added_ids,
    }
    if failed_files:
        response_data["warnings"] = f"Processing failed for files: {', '.join(failed_files)}"
        # Consider if partial success should change the overall status/message
    return response_data


async def documents_upload_job_start(
    *,
    collection_id: str,
    user_id: str,
    files: list[_AsyncReadable],
    declared_content_length: str | None,
    metadatas_json: str | None,
    schedule: Callable[..., Any],
) -> UploadJobStartResponse:
    """Start an async upload/embedding job and return immediately.

    Poll /collections/{collection_id}/documents/upload-jobs/status to track
    progress. Progress survives page navigation on the frontend since it is
    tracked server-side, keyed by collection_id.
    """
    check_batch_size(file_count=len(files), declared_content_length=declared_content_length)
    await ensure_not_connector_managed_collection(str(collection_id))
    ensure_collection_mutable(str(collection_id))

    # Validate the collection exists and this user has write access up front,
    # matching the synchronous endpoint's 404 behavior.
    collection = Collection(collection_id=str(collection_id), user_id=user_id)
    await collection.ensure_exists("write")

    if not metadatas_json:
        metadatas: list[dict] | list[None] = [None] * len(files)
    else:
        try:
            metadatas = _metadata_adapter.validate_json(metadatas_json)
        except ValidationError as e:
            raise BadRequestError(
                code="document.invalid_metadata",
                message_key="errors.rag.document.invalid_metadata",
                details={"errors": e.errors(include_context=False)},
            ) from e
        if len(metadatas) != len(files):
            raise BadRequestError(
                code="document.metadata_count_mismatch",
                message_key="errors.rag.document.metadata_count_mismatch",
                message_params={
                    "metadata_count": len(metadatas),
                    "file_count": len(files),
                },
            )

    existing = document_upload_service.get_upload_progress(str(collection_id))
    if existing is not None and existing.status in document_upload_service.ACTIVE_UPLOAD_STATUSES:
        return UploadJobStartResponse(
            collection_id=str(collection_id),
            status=existing.status,
            message=t("document.upload_already_in_progress"),
        )

    # Read file contents up-front and convert to framework-agnostic DTOs.
    # Starlette closes the original UploadFile handles once this request
    # finishes, which happens before a BackgroundTasks callback gets a
    # chance to read from them, so every file must be fully spooled to its
    # own temp file here. run_upload_job (the background task) owns
    # cleaning those files up once it has actually processed each one --
    # not this handler, which returns long before that happens.
    file_dtos: list[FileUploadDTO] = await read_files_within_total_limit(files)

    document_upload_service.initialize_upload_progress(str(collection_id), total_files=len(files))
    schedule(
        document_upload_service.run_upload_job,
        str(collection_id),
        user_id,
        file_dtos,
        metadatas,
    )

    return UploadJobStartResponse(
        collection_id=str(collection_id),
        status="pending",
        message=t("document.upload_started"),
    )


async def documents_upload_job_status(
    collection_id: str,
    user_id: str,
) -> UploadProgress | None:
    """Get the current upload job progress for a collection.

    Returns ``null`` when no upload job has ever been started for this
    collection.
    """
    # Ensure the collection exists and is readable by this user before exposing
    # any progress for it.
    collection = Collection(collection_id=str(collection_id), user_id=user_id)
    await collection.ensure_exists()

    return document_upload_service.get_upload_progress(str(collection_id))


async def documents_list(
    collection_id: str,
    user_id: str,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    """Lists documents within a specific collection."""
    collection = Collection(
        collection_id=str(collection_id),
        user_id=user_id,
    )
    return await collection.list(limit=limit, offset=offset)


async def documents_list_chunks(
    collection_id: str,
    user_id: str,
    document_id: str,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    """Lists a page of chunks (plus file-level stats) for a document (file_id).

    Chunks are paginated — large files can have thousands of chunks, and
    fetching them all in one response is heavy on both Milvus and the
    browser. Use `stats.total_chunks` / `has_more` to drive incremental
    loading on the client.
    """
    collection = Collection(
        collection_id=str(collection_id),
        user_id=user_id,
    )
    stats = await collection.get_chunk_stats(file_id=document_id)
    chunks = await collection.get_chunks(file_id=document_id, limit=limit, offset=offset)

    return {
        "stats": stats,
        "chunks": chunks,
        "total_chunks": stats["total_chunks"],
        "has_more": offset + len(chunks) < stats["total_chunks"],
    }


async def documents_delete(
    collection_id: str,
    user_id: str,
    document_id: str,
) -> dict[str, bool]:
    """Deletes a specific document from a collection by its ID."""
    await ensure_not_connector_managed_collection(str(collection_id))
    ensure_collection_mutable(str(collection_id))

    collection = Collection(
        collection_id=str(collection_id),
        user_id=user_id,
    )
    # TODO(Eugene): Deletion logic does not look correct.
    #  Should I be deleting by ID or file ID?
    # Raises DependencyUnavailableError (503) on an actual backend failure;
    # a nonexistent file_id is not detectable here (see Collection.delete)
    # and is not treated as an error.
    await collection.delete(file_id=document_id)

    return {"success": True}


async def documents_search(
    collection_id: str,
    user_id: str,
    search_query: SearchQuery,
) -> list[SearchResult]:
    """Search for documents within a specific collection."""
    if not search_query.query:
        raise BadRequestError(
            code="document.search_query_empty",
            message_key="errors.rag.document.search_query_empty",
        )

    collection = Collection(
        collection_id=str(collection_id),
        user_id=user_id,
    )

    results = await collection.search(
        search_query.query,
        limit=search_query.limit or 10,
    )
    return results
