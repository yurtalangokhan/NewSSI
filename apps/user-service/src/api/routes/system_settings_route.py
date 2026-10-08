from typing import Annotated, Any

from error_contract import ApplicationError, render_error_message
from fastapi import APIRouter, Body, Depends, Request, Response

from src.api.dependencies import require_permission
from src.controller.system_settings_controller import get_system_settings_controller
from src.core.response_errors import request_locale, set_error_response
from src.core.response_models import ErrorModel, ResponseModel
from src.schema.system_settings import KeycloakConfigUpdate, KeycloakRealmSessionUpdate

router = APIRouter(prefix="/system-settings", tags=["system-settings"])


@router.get("/keycloak")
async def get_keycloak_settings(
    request: Request,
    response: Response,
    _user_id: Annotated[str, Depends(require_permission("system.settings:read"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(statusCode=200, data=await get_system_settings_controller().get_keycloak_settings())
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.patch("/keycloak")
async def update_keycloak_settings(
    request: Request,
    response: Response,
    payload: Annotated[KeycloakConfigUpdate, Body()],
    _user_id: Annotated[str, Depends(require_permission("system.settings:update"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_system_settings_controller().update_keycloak_settings(payload),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.patch("/keycloak/realm-session")
async def update_realm_session_settings(
    request: Request,
    response: Response,
    payload: Annotated[KeycloakRealmSessionUpdate, Body()],
    _user_id: Annotated[str, Depends(require_permission("system.settings:update"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_system_settings_controller().update_realm_session_settings(payload),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.post("/keycloak/external-idp/sync")
async def sync_external_identity_provider(
    request: Request,
    response: Response,
    _user_id: Annotated[str, Depends(require_permission("system.settings:update"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_system_settings_controller().sync_external_identity_provider(),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )
