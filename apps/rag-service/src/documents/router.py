# Copyright (c) 2026 Agentic AI Platform
from typing import Annotated, Any
from uuid import UUID

from error_contract import ApplicationError, render_error_message
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Query,
    Request,
    Response,
    UploadFile,
)

from src.documents import controller
from src.documents.schemas import (
    FileUploadDTO,
    SearchQuery,
    SearchResult,
    UploadJobStartResponse,
    UploadProgress,
)
from src.documents.upload_limits import (
    check_batch_size as _check_batch_size,
    read_files_within_total_limit as _read_files_within_total_limit_raw,
)
from src.shared.auth import AuthenticatedUser, require_permission
from src.shared.response_errors import request_locale, set_error_response
from src.shared.response_models import ErrorModel, ResponseModel

router = APIRouter(tags=["documents"])


def _check_upload_batch_size(request: Request, files: list[UploadFile]) -> None:
    """Apply the framework-independent upload limit guard."""
    _check_batch_size(
        file_count=len(files),
        declared_content_length=request.headers.get("content-length"),
    )


async def _read_files_within_total_limit(
    files: list[UploadFile],
) -> list[FileUploadDTO]:
    """Read uploads within the configured aggregate size limit."""
    return await _read_files_within_total_limit_raw(files)


@router.post(
    "/collections/{collection_id}/documents",
    response_model=ResponseModel[dict[str, Any]],
)
async def documents_create(
    *,
    response: Response,
    user: Annotated[AuthenticatedUser, Depends(require_permission("document:create"))],
    collection_id: UUID,
    request: Request,
    files: Annotated[list[UploadFile], File()] = ...,
    metadatas_json: Annotated[str | None, Form()] = None,
):
    """Delegate document ingestion to the domain upload service."""
    try:
        data = await controller.documents_create(
            collection_id=str(collection_id),
            user_id=user.identity,
            files=files,
            declared_content_length=request.headers.get("content-length"),
            metadatas_json=metadatas_json,
        )
        return ResponseModel(statusCode=200, data=data)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.post(
    "/collections/{collection_id}/documents/upload-jobs",
    response_model=ResponseModel[UploadJobStartResponse],
    status_code=202,
)
async def documents_upload_job_start(
    *,
    response: Response,
    user: Annotated[AuthenticatedUser, Depends(require_permission("document:create"))],
    collection_id: UUID,
    background_tasks: BackgroundTasks,
    request: Request,
    files: Annotated[list[UploadFile], File()] = ...,
    metadatas_json: Annotated[str | None, Form()] = None,
):
    """Delegate background upload scheduling to the domain service."""
    try:
        data = await controller.documents_upload_job_start(
            collection_id=str(collection_id),
            user_id=user.identity,
            files=files,
            declared_content_length=request.headers.get("content-length"),
            metadatas_json=metadatas_json,
            schedule=background_tasks.add_task,
        )
        return ResponseModel(statusCode=202, data=data)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get(
    "/collections/{collection_id}/documents/upload-jobs/status",
    response_model=ResponseModel[UploadProgress | None],
)
async def documents_upload_job_status(
    *,
    response: Response,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("document:read"))],
    collection_id: UUID,
):
    """Return the current upload progress for an accessible collection."""
    try:
        data = await controller.documents_upload_job_status(
            collection_id=str(collection_id),
            user_id=user.identity,
        )
        return ResponseModel(statusCode=200, data=data)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get(
    "/collections/{collection_id}/documents",
    response_model=ResponseModel[list[dict[str, Any]]],
)
async def documents_list(
    *,
    response: Response,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("document:read"))],
    collection_id: UUID,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Return the requested document page for an accessible collection."""
    try:
        data = await controller.documents_list(
            collection_id=str(collection_id),
            user_id=user.identity,
            limit=limit,
            offset=offset,
        )
        return ResponseModel(statusCode=200, data=data)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get(
    "/collections/{collection_id}/documents/{document_id}/chunks",
    response_model=ResponseModel[dict[str, Any]],
)
async def documents_list_chunks(
    *,
    response: Response,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("document:read"))],
    collection_id: UUID,
    document_id: str,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Return a document chunk page after collection access checks."""
    try:
        data = await controller.documents_list_chunks(
            collection_id=str(collection_id),
            user_id=user.identity,
            document_id=document_id,
            limit=limit,
            offset=offset,
        )
        return ResponseModel(statusCode=200, data=data)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.delete(
    "/collections/{collection_id}/documents/{document_id}",
    response_model=ResponseModel[dict[str, bool]],
)
async def documents_delete(
    *,
    response: Response,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("document:delete"))],
    collection_id: UUID,
    document_id: str,
):
    """Delete the requested document after collection write checks."""
    try:
        data = await controller.documents_delete(
            collection_id=str(collection_id),
            user_id=user.identity,
            document_id=document_id,
        )
        return ResponseModel(statusCode=200, data=data)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.post(
    "/collections/{collection_id}/documents/search",
    response_model=ResponseModel[list[SearchResult]],
)
async def documents_search(
    *,
    response: Response,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("document:search"))],
    collection_id: UUID,
    search_query: SearchQuery,
):
    """Search an accessible collection for matching document chunks."""
    try:
        data = await controller.documents_search(
            collection_id=str(collection_id),
            user_id=user.identity,
            search_query=search_query,
        )
        return ResponseModel(statusCode=200, data=data)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )
