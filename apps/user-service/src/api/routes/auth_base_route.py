from typing import Annotated, Any

from error_contract import ApplicationError, render_error_message
from fastapi import APIRouter, Depends, Form, Query, Request, Response

from src.api.dependencies import require_auth, require_permission
from src.controller import get_auth_controller
from src.core.response_errors import request_locale, set_error_response
from src.core.response_models import ErrorModel, ResponseModel

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/type")
async def get_auth_type(
    request: Request,
    response: Response,
) -> ResponseModel[Any]:
    try:
        return ResponseModel(statusCode=200, data=await get_auth_controller().get_auth_type())
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.post("/login")
async def login(
    request: Request,
    response: Response,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_auth_controller().login(response, username, password),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.post("/external/login")
async def external_login(
    request: Request,
    response: Response,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    redirect_uri: Annotated[str | None, Query()] = None,
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_auth_controller().external_login(
                response,
                username,
                password,
                redirect_uri,
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


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    post_logout_redirect_uri: Annotated[str | None, Query()] = None,
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_auth_controller().logout(request, response, post_logout_redirect_uri),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.post("/refresh")
async def refresh(
    request: Request,
    response: Response,
) -> ResponseModel[Any]:
    try:
        return ResponseModel(statusCode=200, data=await get_auth_controller().refresh(request, response))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("/oidc/authorize")
async def oidc_authorize(
    request: Request,
    response: Response,
    redirect_uri: str | None = None,
    kc_idp_hint: str | None = None,
    prompt: str | None = None,
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_auth_controller().oidc_authorize(redirect_uri, kc_idp_hint, prompt),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("/oidc/callback")
async def oidc_callback(
    request: Request,
    response: Response,
    code: str,
    redirect_uri: str | None = None,
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_auth_controller().oidc_callback(request, response, code, redirect_uri),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("/me")
async def get_me(
    response: Response,
    request: Request,
    user_id: Annotated[str, Depends(require_auth)],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(statusCode=200, data=await get_auth_controller().get_me(request, user_id))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.post("/sync-users")
async def sync_users(
    request: Request,
    response: Response,
    _admin_id: Annotated[str, Depends(require_permission("user:manage"))],
) -> ResponseModel[Any]:
    """Sync users and roles from Keycloak into the local application DB."""
    try:
        return ResponseModel(statusCode=200, data=await get_auth_controller().sync_users_from_keycloak())
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )
