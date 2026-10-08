"""
Thread CRUD routes.

Endpoints: POST /threads/search, POST /threads, GET /threads/{id},
GET /threads/{id}/state, PATCH /threads/{id}, DELETE /threads/{id}
"""

from typing import Annotated, Any

from error_contract import ApplicationError
from error_contract.localization import render_error_message
from fastapi import APIRouter, Body, Depends, Request, Response

from api.dependencies import require_permission, require_user
from api.helpers.thread_helpers import sanitize_checkpoint_values
from api.thread_access import require_owned_thread, resolve_owner_ids
from core.http.response_errors import request_locale, set_error_response
from core.http.response_models import ErrorModel, ResponseModel
from core.observability.logger import get_logger
from schemas.common import StatusResponse
from schemas.threads import (
    ThreadCreateRequest,
    ThreadResponse,
    ThreadSearchRequest,
    ThreadState,
    ThreadUpdateRequest,
)
from service.auth.auth_service import AuthenticatedUser
from service.threads import ThreadAccessService, get_thread_access_service, thread_application_service

logger = get_logger(__name__)

router = APIRouter(prefix="/threads", tags=["threads"], dependencies=[Depends(require_user)])


def _get_service() -> ThreadAccessService:
    return get_thread_access_service()


# =============================================================================
# Helpers
# =============================================================================


_sanitize_checkpoint_values = sanitize_checkpoint_values

# =============================================================================
# Routes
# =============================================================================


@router.post("/search", response_model=ResponseModel[list[ThreadResponse]])
async def search_threads(
    response: Response,
    body: Annotated[ThreadSearchRequest, Body(default_factory=ThreadSearchRequest)],
    user: Annotated[AuthenticatedUser, Depends(require_permission("thread:search"))],
    request: Request = None,
) -> ResponseModel[Any]:
    try:
        owner_ids = await resolve_owner_ids(request, user)
        return ResponseModel(
            data=await thread_application_service.search_threads(
                _get_service(), body.limit, body.offset, body.metadata, owner_ids
            )
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("", response_model=ResponseModel[ThreadResponse])
async def create_thread(
    response: Response,
    body: ThreadCreateRequest,
    user: Annotated[AuthenticatedUser, Depends(require_permission("thread:create"))],
    request: Request = None,
) -> ResponseModel[Any]:
    try:
        metadata = dict(body.metadata or {})
        metadata["user_id"] = user.user_id
        return ResponseModel(
            data=await thread_application_service.create_thread(_get_service(), body.thread_id, metadata)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/{thread_id}", response_model=ResponseModel[ThreadResponse])
async def get_thread(
    response: Response,
    thread_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("thread:read"))],
    request: Request = None,
) -> ResponseModel[Any]:
    try:
        return ResponseModel(data=await require_owned_thread(thread_id, request, user))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/{thread_id}/state", response_model=ResponseModel[ThreadState])
async def get_thread_state(
    response: Response,
    thread_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("thread:read"))],
    request: Request = None,
) -> ResponseModel[Any]:
    try:
        await require_owned_thread(thread_id, request, user)
        return ResponseModel(data=await thread_application_service.get_thread_state(_get_service(), thread_id))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.patch("/{thread_id}", response_model=ResponseModel[ThreadResponse])
async def update_thread(
    response: Response,
    thread_id: str,
    body: ThreadUpdateRequest,
    user: Annotated[AuthenticatedUser, Depends(require_permission("thread:update"))],
    request: Request = None,
) -> ResponseModel[Any]:
    try:
        await require_owned_thread(thread_id, request, user)
        return ResponseModel(
            data=await thread_application_service.update_thread(_get_service(), thread_id, body.metadata)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.delete("/{thread_id}", response_model=ResponseModel[StatusResponse])
async def delete_thread(
    response: Response,
    thread_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("thread:delete"))],
    request: Request = None,
) -> ResponseModel[Any]:
    try:
        await require_owned_thread(thread_id, request, user)
        return ResponseModel(data=await thread_application_service.delete_thread(_get_service(), thread_id))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))
