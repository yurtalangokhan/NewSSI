# Copyright (c) 2026 Agentic AI Platform
"""Collection JSON transport using the service-local response model."""

from typing import Annotated
from uuid import UUID

from error_contract import ApplicationError, render_error_message
from fastapi import APIRouter, Depends, Request, Response

from src.collections import controller
from src.collections.schemas import (
    CollectionCreate,
    CollectionResponse,
    CollectionUpdate,
)
from src.shared.auth import AuthenticatedUser, require_permission
from src.shared.response_errors import request_locale, set_error_response
from src.shared.response_models import ErrorModel, ResponseModel

router = APIRouter(prefix="/collections", tags=["collections"])


@router.post("", response_model=ResponseModel[CollectionResponse], status_code=201)
async def collections_create(
    response: Response,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("collection:create"))],
    collection_data: CollectionCreate,
):
    """Create collection metadata for the requesting user."""
    try:
        data = await controller.create(user.identity, collection_data)
        return ResponseModel(statusCode=201, data=data)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("", response_model=ResponseModel[list[CollectionResponse]], status_code=200)
async def collections_list(
    response: Response,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("collection:list"))],
):
    """List collections visible to the requesting user."""
    try:
        data = await controller.list_collections(user.identity)
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
    "/{collection_id}",
    response_model=ResponseModel[CollectionResponse],
    status_code=200,
)
async def collections_get(
    response: Response,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("collection:read"))],
    collection_id: UUID,
):
    """Resolve the requested collection for the requesting user."""
    try:
        data = await controller.get(user.identity, str(collection_id))
        return ResponseModel(statusCode=200, data=data)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.delete("/{collection_id}", response_model=ResponseModel[None], status_code=200)
async def collections_delete(
    response: Response,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("collection:delete"))],
    collection_id: UUID,
):
    """Delete an accessible collection after mutation guards pass."""
    try:
        await controller.delete(user.identity, str(collection_id))
        return ResponseModel(statusCode=200, data=None)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.delete("/{collection_id}/force", response_model=ResponseModel[None], status_code=200)
async def collections_force_delete(
    response: Response,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("collection:delete"))],
    collection_id: UUID,
):
    """Delete an accessible collection while allowing connector metadata."""
    try:
        await controller.delete(user.identity, str(collection_id), force=True)
        return ResponseModel(statusCode=200, data=None)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.patch(
    "/{collection_id}",
    response_model=ResponseModel[CollectionResponse],
    status_code=200,
)
async def collections_update(
    response: Response,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("collection:update"))],
    collection_id: UUID,
    collection_data: CollectionUpdate,
):
    """Update collection metadata after mutation guards pass."""
    try:
        data = await controller.update(user.identity, str(collection_id), collection_data)
        return ResponseModel(statusCode=200, data=data)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )
