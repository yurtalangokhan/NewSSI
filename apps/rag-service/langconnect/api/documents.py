import logging
from typing import Annotated, Any
from uuid import UUID

from error_contract import ApplicationError
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from i18n import t
from langchain_core.documents import Document
from pydantic import TypeAdapter, ValidationError

from langconnect.auth import AuthenticatedUser, require_permission
from langconnect.models import SearchQuery, SearchResult
from langconnect.models.documents import (
    FileUploadDTO,
    UploadJobStartResponse,
    UploadProgress,
)
from langconnect.services import document_upload_service, process_document
from langconnect.services.build_lock import (
    ensure_collection_mutable,
    ensure_not_connector_managed_collection,
)
from langconnect.services.collections import Collection

# Create a TypeAdapter that enforces “list of dict”
_metadata_adapter = TypeAdapter(list[dict[str, Any]])

logger = logging.getLogger(__name__)

router = APIRouter(tags=["documents"])


async def _upload_file_to_dto(file: UploadFile) -> FileUploadDTO:
    """Read a FastAPI ``UploadFile`` into a framework-agnostic DTO.

    All byte reading happens here, at the API boundary, so downstream
    services never depend on FastAPI or Starlette types.
    """
    content = await file.read()
    return FileUploadDTO(
        filename=file.filename or "",
        content_type=file.content_type,
        size=len(content),
        content=content,
    )


@router.post("/collections/{collection_id}/documents", response_model=dict[str, Any])
async def documents_create(
    user: Annotated[AuthenticatedUser, Depends(require_permission("document:create"))],
    collection_id: UUID,
    files: list[UploadFile] = File(...),
    metadatas_json: str | None = Form(None),
):
    """Processes and indexes (adds) new document files with optional metadata."""
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
            # Pydantic errors include exactly what went wrong. Left untranslated
            # intentionally: these come from pydantic itself, not our locale
            # files, and changing `detail` from a list to something else would
            # break any client parsing these as structured field errors.
            raise HTTPException(status_code=400, detail=e.errors())
        # Now just check that the list length matches
        if len(metadatas) != len(files):
            raise HTTPException(
                status_code=400,
                detail=t(
                    "document.metadata_count_mismatch",
                    metadata_count=len(metadatas),
                    file_count=len(files),
                ),
            )

    docs_to_index: list[Document] = []
    processed_files_count = 0
    failed_files = []

    # Convert UploadFile objects to framework-agnostic DTOs once, up-front,
    # so that all downstream code (services, processors) never sees FastAPI
    # types.
    file_dtos: list[FileUploadDTO] = [await _upload_file_to_dto(f) for f in files]

    # Pair files with their corresponding metadata
    for file_dto, metadata in zip(file_dtos, metadatas, strict=False):
        try:
            # Pass metadata to process_document
            langchain_docs = await process_document(file_dto, metadata=metadata)
            if langchain_docs:
                docs_to_index.extend(langchain_docs)
                processed_files_count += 1
            else:
                logger.info(
                    f"Warning: File {file_dto.filename} resulted "
                    f"in no processable documents."
                )
                # Decide if this constitutes a failure
                # failed_files.append(file_dto.filename)

        except Exception as proc_exc:
            # Log the error and the file that caused it
            logger.info(f"Error processing file {file_dto.filename}: {proc_exc}")
            failed_files.append(file_dto.filename)
            # Decide on behavior: continue processing others or fail fast?
            # For now, let's collect failures and report them, but continue processing.

    # If after processing all files, none yielded documents, raise error
    if not docs_to_index:
        error_detail = t("document.no_documents_processed")
        if failed_files:
            error_detail += t(
                "document.failed_files_list", files=", ".join(failed_files)
            )
        raise HTTPException(status_code=400, detail=error_detail)

    # If some files failed but others succeeded, proceed with adding successful ones
    # but maybe inform the user about the failures.
    try:
        collection = Collection(
            collection_id=str(collection_id),
            user_id=user.identity,
        )
        added_ids = await collection.upsert(docs_to_index)
        if not added_ids:
            # This might indicate a problem with the vector store itself
            raise HTTPException(
                status_code=500,
                detail=t("document.vectorstore_add_failed"),
            )

        # Construct response message
        success_message = (
            f"{len(added_ids)} document chunk(s) from "
            f"{processed_files_count} file(s) added successfully."
        )
        response_data = {
            "success": True,
            "message": success_message,
            "added_chunk_ids": added_ids,
        }

        if failed_files:
            response_data["warnings"] = (
                f"Processing failed for files: {', '.join(failed_files)}"
            )
            # Consider if partial success should change the overall status/message

        return response_data

    except (HTTPException, ApplicationError) as http_exc:
        # Reraise edge/domain exceptions from vector store operations.
        raise http_exc
    except Exception as add_exc:
        # Handle exceptions during the vector store addition process
        logger.info(f"Error adding documents to vector store: {add_exc}")
        raise HTTPException(
            status_code=500,
            detail=f"{t('common.internal_error')}: {add_exc!s}",
        )


@router.post(
    "/collections/{collection_id}/documents/upload-jobs",
    response_model=UploadJobStartResponse,
    status_code=202,
)
async def documents_upload_job_start(
    user: Annotated[AuthenticatedUser, Depends(require_permission("document:create"))],
    collection_id: UUID,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    metadatas_json: str | None = Form(None),
):
    """Start an async upload/embedding job and return immediately.

    Poll /collections/{collection_id}/documents/upload-jobs/status to track
    progress. Progress survives page navigation on the frontend since it is
    tracked server-side, keyed by collection_id.
    """
    await ensure_not_connector_managed_collection(str(collection_id))
    ensure_collection_mutable(str(collection_id))

    # Validate the collection exists (and is owned by this user) up front,
    # matching the synchronous endpoint's 404 behavior.
    collection = Collection(collection_id=str(collection_id), user_id=user.identity)
    await collection.ensure_exists()

    if not metadatas_json:
        metadatas: list[dict] | list[None] = [None] * len(files)
    else:
        try:
            metadatas = _metadata_adapter.validate_json(metadatas_json)
        except ValidationError as e:
            raise HTTPException(status_code=400, detail=e.errors())
        if len(metadatas) != len(files):
            raise HTTPException(
                status_code=400,
                detail=t(
                    "document.metadata_count_mismatch",
                    metadata_count=len(metadatas),
                    file_count=len(files),
                ),
            )

    existing = document_upload_service.get_upload_progress(str(collection_id))
    if (
        existing is not None
        and existing.status in document_upload_service.ACTIVE_UPLOAD_STATUSES
    ):
        return UploadJobStartResponse(
            collection_id=str(collection_id),
            status=existing.status,
            message=t("document.upload_already_in_progress"),
        )

    # Read file contents up-front and convert to framework-agnostic DTOs.
    # Starlette closes the original UploadFile handles once this request
    # finishes, which happens before a BackgroundTasks callback gets a
    # chance to read from them, so all bytes must be consumed here.
    file_dtos: list[FileUploadDTO] = [await _upload_file_to_dto(f) for f in files]

    document_upload_service.initialize_upload_progress(
        str(collection_id), total_files=len(files)
    )
    background_tasks.add_task(
        document_upload_service.run_upload_job,
        str(collection_id),
        user.identity,
        file_dtos,
        metadatas,
    )

    return UploadJobStartResponse(
        collection_id=str(collection_id),
        status="pending",
        message=t("document.upload_started"),
    )


@router.get(
    "/collections/{collection_id}/documents/upload-jobs/status",
    response_model=UploadProgress | None,
)
async def documents_upload_job_status(
    user: Annotated[AuthenticatedUser, Depends(require_permission("document:read"))],
    collection_id: UUID,
):
    """Get the current upload job progress for a collection.

    Returns ``null`` when no upload job has ever been started for this
    collection.
    """
    # Ensure the collection exists and is owned by this user before exposing
    # any progress for it.
    collection = Collection(collection_id=str(collection_id), user_id=user.identity)
    await collection.ensure_exists()

    return document_upload_service.get_upload_progress(str(collection_id))


@router.get(
    "/collections/{collection_id}/documents", response_model=list[dict[str, Any]]
)
async def documents_list(
    user: Annotated[AuthenticatedUser, Depends(require_permission("document:read"))],
    collection_id: UUID,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Lists documents within a specific collection."""
    from langconnect.services.collections import CollectionsManager

    # Connector-managed collections (e.g. Airbyte) are created without owner_id.
    # Use internal access so the ownership filter doesn't block the read.
    internal_col = await CollectionsManager("internal-service").get(str(collection_id))
    if internal_col and (internal_col.get("metadata") or {}).get("connector_type"):
        effective_user = "internal-service"
    else:
        effective_user = user.identity

    collection = Collection(
        collection_id=str(collection_id),
        user_id=effective_user,
    )
    return await collection.list(limit=limit, offset=offset)


@router.get(
    "/collections/{collection_id}/documents/{document_id}/chunks",
    response_model=dict[str, Any],
)
async def documents_list_chunks(
    user: Annotated[AuthenticatedUser, Depends(require_permission("document:read"))],
    collection_id: UUID,
    document_id: str,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Lists a page of chunks (plus file-level stats) for a document (file_id).

    Chunks are paginated — large files can have thousands of chunks, and
    fetching them all in one response is heavy on both Milvus and the
    browser. Use `stats.total_chunks` / `has_more` to drive incremental
    loading on the client.
    """
    collection = Collection(
        collection_id=str(collection_id),
        user_id=user.identity,
    )
    stats = await collection.get_chunk_stats(file_id=document_id)
    chunks = await collection.get_chunks(
        file_id=document_id, limit=limit, offset=offset
    )

    return {
        "stats": stats,
        "chunks": chunks,
        "total_chunks": stats["total_chunks"],
        "has_more": offset + len(chunks) < stats["total_chunks"],
    }


@router.delete(
    "/collections/{collection_id}/documents/{document_id}",
    response_model=dict[str, bool],
)
async def documents_delete(
    user: Annotated[AuthenticatedUser, Depends(require_permission("document:delete"))],
    collection_id: UUID,
    document_id: str,
):
    """Deletes a specific document from a collection by its ID."""
    await ensure_not_connector_managed_collection(str(collection_id))
    ensure_collection_mutable(str(collection_id))

    collection = Collection(
        collection_id=str(collection_id),
        user_id=user.identity,
    )
    # TODO(Eugene): Deletion logic does not look correct.
    #  Should I be deleting by ID or file ID?
    success = await collection.delete(file_id=document_id)
    if not success:
        raise HTTPException(status_code=404, detail=t("document.delete_failed"))

    return {"success": True}


@router.post(
    "/collections/{collection_id}/documents/search", response_model=list[SearchResult]
)
async def documents_search(
    user: Annotated[AuthenticatedUser, Depends(require_permission("document:search"))],
    collection_id: UUID,
    search_query: SearchQuery,
):
    """Search for documents within a specific collection."""
    if not search_query.query:
        raise HTTPException(status_code=400, detail=t("document.search_query_empty"))

    collection = Collection(
        collection_id=str(collection_id),
        user_id=user.identity,
    )

    results = await collection.search(
        search_query.query,
        limit=search_query.limit or 10,
    )
    return results
