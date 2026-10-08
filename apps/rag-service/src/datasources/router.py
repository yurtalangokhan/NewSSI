# Copyright (c) 2026 Agentic AI Platform
"""HTTP adapter for knowledge selection and connector-managed records."""

from typing import Annotated
from uuid import UUID

from error_contract import ApplicationError, render_error_message
from fastapi import APIRouter, Depends, Request, Response

from src.datasources import controller
from src.datasources.schemas import (
    DatasourceEntitiesResponse,
    DatasourceRecordsDeleteResponse,
    DatasourceRecordsIngestRequest,
    DatasourceRecordsIngestResponse,
    DatasourceRecordsRetireRequest,
    DatasourceRecordsRetireResponse,
    KnowledgeSelectorResponse,
)
from src.shared.auth import AuthenticatedUser, require_permission
from src.shared.response_errors import request_locale, set_error_response
from src.shared.response_models import ErrorModel, ResponseModel

router = APIRouter(prefix="/datasources", tags=["datasources"])


@router.get("/knowledge-selector", response_model=ResponseModel[KnowledgeSelectorResponse])
async def knowledge_selector(
    *,
    response: Response,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("datasource:read"))],
):
    """Return knowledge sources visible to the current user."""
    try:
        data = await controller.knowledge_selector(user.identity)
        return ResponseModel(data=data)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.post(
    "/{collection_id}/records",
    response_model=ResponseModel[DatasourceRecordsIngestResponse],
)
async def ingest_datasource_records(
    *,
    response: Response,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("datasource:sync"))],
    collection_id: UUID,
    body: DatasourceRecordsIngestRequest,
):
    """Chunk, embed, and store connector-managed records."""
    try:
        data = await controller.ingest_datasource_records(
            user.identity,
            str(collection_id),
            body.documents,
            clear_existing=body.clear_existing,
        )
        return ResponseModel(data=data)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.post(
    "/{collection_id}/records/retire",
    response_model=ResponseModel[DatasourceRecordsRetireResponse],
)
async def retire_datasource_runs(
    *,
    response: Response,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("datasource:sync"))],
    collection_id: UUID,
    body: DatasourceRecordsRetireRequest,
):
    """Keep the chunks of one sync run; remove every other chunk (the end of an overwrite sync)."""
    try:
        data = await controller.retire_datasource_runs(user.identity, str(collection_id), body.keep_job_id)
        return ResponseModel(data=data)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.delete(
    "/{collection_id}/records",
    response_model=ResponseModel[DatasourceRecordsDeleteResponse],
)
async def delete_datasource_records(
    *,
    response: Response,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("datasource:sync"))],
    collection_id: UUID,
):
    """Drop every chunk of a datasource (its Milvus table): agent-service is deleting it."""
    try:
        data = await controller.delete_datasource_records(user.identity, str(collection_id))
        return ResponseModel(data=data)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get(
    "/{collection_id}/entities",
    response_model=ResponseModel[DatasourceEntitiesResponse],
)
async def list_datasource_entities(
    *,
    response: Response,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("datasource:read"))],
    collection_id: UUID,
    limit: int = 10,
    offset: int = 0,
    include_stats: bool = False,
):
    """Return raw connector entities and optional size statistics."""
    try:
        data = await controller.list_datasource_entities(
            user.identity,
            str(collection_id),
            limit,
            offset,
            include_stats=include_stats,
        )
        return ResponseModel(data=data)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )
