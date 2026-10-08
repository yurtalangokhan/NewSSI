from typing import Annotated, Any

from error_contract import ApplicationError, render_error_message
from fastapi import APIRouter, Body, Depends, Request, Response

from src.api.dependencies import require_auth_or_internal_service_token, require_permission
from src.controller import get_settings_controller
from src.controller.user_controller import get_user_controller
from src.core.response_errors import request_locale, set_error_response
from src.core.response_models import ErrorModel, ResponseModel

router = APIRouter(prefix="/users/me/settings", tags=["settings"])
internal_router = APIRouter(prefix="/internal/users", tags=["settings"])


@router.get("/")
async def get_settings(
    request: Request,
    response: Response,
    user_id: Annotated[str, Depends(require_permission("settings:read"))],
) -> ResponseModel[dict[str, Any]]:
    try:
        data = await get_settings_controller().get_settings(user_id)
        return ResponseModel(data=data)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.patch("/")
async def update_settings(
    request: Request,
    response: Response,
    updates: Annotated[dict[str, Any], Body()],
    user_id: Annotated[str, Depends(require_permission("settings:update"))],
) -> ResponseModel[dict[str, Any]]:
    try:
        data = await get_settings_controller().update_settings(user_id, **updates)
        return ResponseModel(data=data)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.post("/prompt-shortcuts")
async def create_prompt_shortcut(
    request: Request,
    response: Response,
    shortcut: Annotated[dict[str, Any], Body()],
    user_id: Annotated[str, Depends(require_permission("settings:update"))],
) -> ResponseModel[dict[str, Any]]:
    try:
        data = await get_settings_controller().create_prompt_shortcut(user_id, shortcut)
        return ResponseModel(data=data)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.patch("/prompt-shortcuts/{shortcut_id}")
async def update_prompt_shortcut(
    request: Request,
    response: Response,
    shortcut_id: int,
    updates: Annotated[dict[str, Any], Body()],
    user_id: Annotated[str, Depends(require_permission("settings:update"))],
) -> ResponseModel[dict[str, Any]]:
    try:
        data = await get_settings_controller().update_prompt_shortcut(user_id, shortcut_id, **updates)
        return ResponseModel(data=data)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.delete("/prompt-shortcuts/{shortcut_id}")
async def delete_prompt_shortcut(
    request: Request,
    response: Response,
    shortcut_id: int,
    user_id: Annotated[str, Depends(require_permission("settings:update"))],
) -> ResponseModel[dict[str, Any]]:
    try:
        data = await get_settings_controller().delete_prompt_shortcut(user_id, shortcut_id)
        return ResponseModel(data=data)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@internal_router.get("/{target_id}/settings")
async def get_settings_internal(
    request: Request,
    response: Response,
    target_id: str,
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
) -> ResponseModel[dict[str, Any]]:
    try:
        resolved_user_id = await get_user_controller().authorize_target_user_id(
            target_id,
            authenticated_user_id,
        )
        data = await get_settings_controller().get_settings(resolved_user_id)
        return ResponseModel(data=data)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@internal_router.patch("/{target_id}/settings")
async def update_settings_internal(
    request: Request,
    response: Response,
    target_id: str,
    updates: Annotated[dict[str, Any], Body()],
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
) -> ResponseModel[dict[str, Any]]:
    try:
        resolved_user_id = await get_user_controller().authorize_target_user_id(
            target_id,
            authenticated_user_id,
        )
        data = await get_settings_controller().update_settings(resolved_user_id, **updates)
        return ResponseModel(data=data)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@internal_router.post("/{target_id}/settings/prompt-shortcuts")
async def create_prompt_shortcut_internal(
    request: Request,
    response: Response,
    target_id: str,
    shortcut: Annotated[dict[str, Any], Body()],
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
) -> ResponseModel[dict[str, Any]]:
    try:
        resolved_user_id = await get_user_controller().authorize_target_user_id(
            target_id,
            authenticated_user_id,
        )
        data = await get_settings_controller().create_prompt_shortcut(resolved_user_id, shortcut)
        return ResponseModel(data=data)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@internal_router.patch(
    "/{target_id}/settings/prompt-shortcuts/{shortcut_id}",
)
async def update_prompt_shortcut_internal(
    request: Request,
    response: Response,
    target_id: str,
    shortcut_id: int,
    updates: Annotated[dict[str, Any], Body()],
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
) -> ResponseModel[dict[str, Any]]:
    try:
        resolved_user_id = await get_user_controller().authorize_target_user_id(
            target_id,
            authenticated_user_id,
        )
        data = await get_settings_controller().update_prompt_shortcut(resolved_user_id, shortcut_id, **updates)
        return ResponseModel(data=data)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@internal_router.delete(
    "/{target_id}/settings/prompt-shortcuts/{shortcut_id}",
)
async def delete_prompt_shortcut_internal(
    request: Request,
    response: Response,
    target_id: str,
    shortcut_id: int,
    authenticated_user_id: Annotated[str, Depends(require_auth_or_internal_service_token)],
) -> ResponseModel[dict[str, Any]]:
    try:
        resolved_user_id = await get_user_controller().authorize_target_user_id(
            target_id,
            authenticated_user_id,
        )
        data = await get_settings_controller().delete_prompt_shortcut(resolved_user_id, shortcut_id)
        return ResponseModel(data=data)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )
