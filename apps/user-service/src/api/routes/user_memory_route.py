from typing import Annotated, Any
import uuid

from error_contract import ApplicationError, render_error_message
from fastapi import APIRouter, Body, Depends, Query, Request, Response

from src.api.dependencies import require_auth_or_internal_service_token, require_permission
from src.controller import get_user_memory_controller
from src.controller.base import BaseController
from src.controller.user_controller import get_user_controller
from src.core.response_errors import request_locale, set_error_response
from src.core.response_models import ErrorModel, ResponseModel
from src.schema.memory import MemoryFactsRequest, MemoryWriteRequest

router = APIRouter(prefix="/users/me/memories", tags=["user-memory"])
internal_router = APIRouter(prefix="/internal/users", tags=["user-memory"])


# ---------------------------------------------------------------------------
# User-facing endpoints
# ---------------------------------------------------------------------------


@router.get("")
async def list_memories(
    request: Request,
    response: Response,
    user_id: Annotated[str, Depends(require_permission("memory:read"))],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_user_memory_controller().list_memories(
                BaseController.parse_user_id(user_id), page=page, page_size=page_size
            ),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.post("", status_code=201)
async def create_memory(
    request: Request,
    response: Response,
    body: Annotated[MemoryWriteRequest, Body()],
    user_id: Annotated[str, Depends(require_permission("memory:create"))],
) -> ResponseModel[Any]:
    try:
        content = body.content
        return ResponseModel(
            statusCode=201,
            data=await get_user_memory_controller().create_memory(BaseController.parse_user_id(user_id), content),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("/{memory_id}")
async def get_memory(
    request: Request,
    response: Response,
    memory_id: uuid.UUID,
    user_id: Annotated[str, Depends(require_permission("memory:read"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_user_memory_controller().get_memory(BaseController.parse_user_id(user_id), memory_id),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.patch("/{memory_id}")
async def update_memory(
    request: Request,
    response: Response,
    memory_id: uuid.UUID,
    body: Annotated[MemoryWriteRequest, Body()],
    user_id: Annotated[str, Depends(require_permission("memory:update"))],
) -> ResponseModel[Any]:
    try:
        content = body.content
        return ResponseModel(
            statusCode=200,
            data=await get_user_memory_controller().update_memory(
                BaseController.parse_user_id(user_id), memory_id, content
            ),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.delete("/{memory_id}", status_code=200)
async def delete_memory(
    request: Request,
    response: Response,
    memory_id: uuid.UUID,
    user_id: Annotated[str, Depends(require_permission("memory:delete"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_user_memory_controller().delete_memory(BaseController.parse_user_id(user_id), memory_id),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.delete("")
async def delete_all_memories(
    request: Request,
    response: Response,
    user_id: Annotated[str, Depends(require_permission("memory:delete"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_user_memory_controller().delete_all_memories(BaseController.parse_user_id(user_id)),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


# ---------------------------------------------------------------------------
# Internal service-to-service endpoints
# ---------------------------------------------------------------------------


@internal_router.get("/{target_id}/memories")
async def list_memories_internal(
    request: Request,
    response: Response,
    target_id: str,
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ResponseModel[Any]:
    try:
        resolved_user_id = await get_user_controller().authorize_target_user_id(
            target_id,
            authenticated_user_id,
        )
        return ResponseModel(
            statusCode=200,
            data=await get_user_memory_controller().list_memories(resolved_user_id, page=page, page_size=page_size),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@internal_router.get("/{target_id}/memories/recall")
async def list_memories_for_recall_internal(
    request: Request,
    response: Response,
    target_id: str,
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
) -> ResponseModel[Any]:
    try:
        resolved_user_id = await get_user_controller().authorize_target_user_id(
            target_id,
            authenticated_user_id,
        )
        return ResponseModel(
            statusCode=200,
            data=await get_user_memory_controller().list_for_recall(resolved_user_id),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@internal_router.post("/{target_id}/memories")
async def create_memory_internal(
    request: Request,
    response: Response,
    target_id: str,
    body: Annotated[MemoryWriteRequest, Body()],
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
) -> ResponseModel[Any]:
    try:
        resolved_user_id = await get_user_controller().authorize_target_user_id(
            target_id,
            authenticated_user_id,
        )
        content = body.content
        return ResponseModel(
            statusCode=200,
            data=await get_user_memory_controller().create_memory(resolved_user_id, content),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@internal_router.post("/{target_id}/memories/bulk")
async def add_facts_internal(
    request: Request,
    response: Response,
    target_id: str,
    body: Annotated[MemoryFactsRequest, Body()],
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
) -> ResponseModel[Any]:
    try:
        resolved_user_id = await get_user_controller().authorize_target_user_id(
            target_id,
            authenticated_user_id,
        )
        contents = body.contents
        source = body.source
        # Absent when the extractor's model declared no language; stored as NULL.
        language = body.language
        return ResponseModel(
            statusCode=200,
            data=await get_user_memory_controller().add_facts(
                resolved_user_id, contents, source=source, language=language
            ),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@internal_router.get("/{target_id}/memories/{memory_id}")
async def get_memory_internal(
    request: Request,
    response: Response,
    target_id: str,
    memory_id: uuid.UUID,
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
) -> ResponseModel[Any]:
    try:
        resolved_user_id = await get_user_controller().authorize_target_user_id(
            target_id,
            authenticated_user_id,
        )
        return ResponseModel(
            statusCode=200,
            data=await get_user_memory_controller().get_memory(resolved_user_id, memory_id),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@internal_router.patch("/{target_id}/memories/{memory_id}")
async def update_memory_internal(
    request: Request,
    response: Response,
    target_id: str,
    memory_id: uuid.UUID,
    body: Annotated[MemoryWriteRequest, Body()],
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
) -> ResponseModel[Any]:
    try:
        resolved_user_id = await get_user_controller().authorize_target_user_id(
            target_id,
            authenticated_user_id,
        )
        content = body.content
        return ResponseModel(
            statusCode=200,
            data=await get_user_memory_controller().update_memory(resolved_user_id, memory_id, content),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@internal_router.delete("/{target_id}/memories/{memory_id}", status_code=200)
async def delete_memory_internal(
    request: Request,
    response: Response,
    target_id: str,
    memory_id: uuid.UUID,
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
) -> ResponseModel[Any]:
    try:
        resolved_user_id = await get_user_controller().authorize_target_user_id(
            target_id,
            authenticated_user_id,
        )
        return ResponseModel(
            statusCode=200,
            data=await get_user_memory_controller().delete_memory(resolved_user_id, memory_id),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@internal_router.delete("/{target_id}/memories")
async def delete_all_memories_internal(
    request: Request,
    response: Response,
    target_id: str,
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
) -> ResponseModel[Any]:
    try:
        resolved_user_id = await get_user_controller().authorize_target_user_id(
            target_id,
            authenticated_user_id,
        )
        return ResponseModel(
            statusCode=200,
            data=await get_user_memory_controller().delete_all_memories(resolved_user_id),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )
