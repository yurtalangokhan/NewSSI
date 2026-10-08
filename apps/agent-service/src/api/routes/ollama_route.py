"""Built-in Ollama management API routes."""

from __future__ import annotations

from typing import Annotated, Any

from error_contract import ApplicationError
from error_contract.localization import render_error_message
from fastapi import APIRouter, Depends, Request, Response

from api.dependencies import AuthenticatedUser, require_permission, require_user
from core.http.response_errors import request_locale, set_error_response
from core.http.response_models import ErrorModel, ResponseModel
from integrations.ollama_repository import OllamaRepository
from schemas.common import SuccessResponse
from schemas.ollama import OllamaModelDetailResponse, OllamaStatusResponse
from service.ollama.ollama_service import OllamaService

router = APIRouter(
    prefix="/api/admin/ollama",
    tags=["ollama"],
    dependencies=[Depends(require_user)],
)

_repo = OllamaRepository()
_svc = OllamaService(_repo)
_service = _svc


@router.get("/status", response_model=ResponseModel[OllamaStatusResponse])
async def get_builtin_ollama_status(
    response: Response,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("provider:read"))],
) -> ResponseModel[Any]:
    _ = user
    try:
        return ResponseModel(data=await _service.get_status())
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("/models", response_model=ResponseModel[list[OllamaModelDetailResponse]])
async def list_builtin_ollama_models(
    response: Response,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_permission("provider:read"))],
) -> ResponseModel[Any]:
    _ = user
    try:
        return ResponseModel(data=await _service.list_models())
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.delete("/models/{model_name:path}", response_model=ResponseModel[SuccessResponse])
async def delete_builtin_ollama_model(
    response: Response,
    request: Request,
    model_name: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("provider:update"))],
) -> ResponseModel[Any]:
    _ = user
    try:
        return ResponseModel(data=await _service.delete_model(model_name))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )
