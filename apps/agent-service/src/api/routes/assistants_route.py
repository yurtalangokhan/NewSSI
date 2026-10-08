"""
Assistant CRUD routes.

Endpoints: POST /assistants/search, GET /assistants/{id},
POST /assistants, PUT|PATCH /assistants/{id}, DELETE /assistants/{id}
"""

from typing import Annotated, Any

from error_contract import ApplicationError
from error_contract.localization import render_error_message
from fastapi import APIRouter, Body, Depends, Request, Response

from api.dependencies import AuthenticatedUser, require_permission, require_user
from core.http.response_errors import request_locale, set_error_response
from core.http.response_models import ErrorModel, ResponseModel
from schemas.assistants import (
    AssistantCreateRequest,
    AssistantDeleteResponse,
    AssistantResponse,
    AssistantSearchRequest,
    AssistantUpdateRequest,
)
from service.orchestration.assistants_application_service import AssistantsApplicationService

router = APIRouter(prefix="/assistants", tags=["assistants"], dependencies=[Depends(require_user)])


@router.post("/search", response_model=ResponseModel[list[AssistantResponse]])
async def search_assistants(
    request: Request,
    response: Response,
    body: Annotated[AssistantSearchRequest, Body(default_factory=AssistantSearchRequest)],
    _user: Annotated[AuthenticatedUser, Depends(require_permission("assistant:search"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await AssistantsApplicationService().search_assistants(request=body),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/{assistant_id}", response_model=ResponseModel[AssistantResponse])
async def get_assistant(
    request: Request,
    response: Response,
    assistant_id: str,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("assistant:read"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await AssistantsApplicationService().get_assistant(assistant_id=assistant_id),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("", response_model=ResponseModel[AssistantResponse])
async def create_assistant(
    request: Request,
    response: Response,
    body: AssistantCreateRequest,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("assistant:create"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await AssistantsApplicationService().create_assistant(request=body),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.patch("/{assistant_id}", response_model=ResponseModel[AssistantResponse])
async def update_assistant(
    request: Request,
    response: Response,
    assistant_id: str,
    body: AssistantUpdateRequest,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("assistant:update"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await AssistantsApplicationService().update_assistant(assistant_id=assistant_id, request=body),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.delete("/{assistant_id}", response_model=ResponseModel[AssistantDeleteResponse])
async def delete_assistant(
    request: Request,
    response: Response,
    assistant_id: str,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("assistant:delete"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await AssistantsApplicationService().delete_assistant(assistant_id=assistant_id),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))
