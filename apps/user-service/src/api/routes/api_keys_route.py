from typing import Annotated, Any
import uuid

from error_contract import ApplicationError, render_error_message
from fastapi import APIRouter, Depends, Request, Response

from src.api.dependencies import require_permission
from src.controller import get_api_key_controller
from src.controller.base import BaseController
from src.core.response_errors import request_locale, set_error_response
from src.core.response_models import ErrorModel, ResponseModel

router = APIRouter(prefix="/users/me/api-keys", tags=["api-keys"])


@router.post("/")
async def create_key(
    request: Request,
    response: Response,
    name: str,
    user_id: Annotated[str, Depends(require_permission("api_key:create"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_api_key_controller().create_key(BaseController.parse_user_id(user_id), name),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("/")
async def list_keys(
    request: Request, response: Response, user_id: Annotated[str, Depends(require_permission("api_key:read"))]
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_api_key_controller().list_keys(BaseController.parse_user_id(user_id)),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.delete("/{key_id}")
async def delete_key(
    request: Request,
    response: Response,
    key_id: uuid.UUID,
    user_id: Annotated[str, Depends(require_permission("api_key:delete"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_api_key_controller().delete_key(key_id, BaseController.parse_user_id(user_id)),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )
