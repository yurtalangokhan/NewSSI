from typing import Any

from error_contract import ApplicationError, render_error_message
from fastapi import APIRouter, Request, Response

from src.controller import get_auth_controller
from src.core.response_errors import request_locale, set_error_response
from src.core.response_models import ErrorModel, ResponseModel
from src.schema.auth import RegisterRequest

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
async def register(
    request: Request,
    response: Response,
    body: RegisterRequest,
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_auth_controller().register(
                response,
                username=body.username,
                email=body.email,
                password=body.password,
                first_name=body.first_name,
                last_name=body.last_name,
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
