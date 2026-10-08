from typing import Annotated, Any

from error_contract import ApplicationError, render_error_message
from fastapi import APIRouter, Depends, Query, Request, Response

from src.api.dependencies import require_permission
from src.controller.permission_controller import get_permission_controller
from src.core.response_errors import request_locale, set_error_response
from src.core.response_models import ErrorModel, ResponseModel

router = APIRouter(prefix="/permissions", tags=["permissions"])


@router.get("/")
async def list_permissions(
    request: Request,
    response: Response,
    _user_id: Annotated[str, Depends(require_permission("permission:list"))],
    service: Annotated[str | None, Query()] = None,
) -> ResponseModel[dict[str, Any]]:
    try:
        ctrl = get_permission_controller()
        return ResponseModel(statusCode=200, data=await ctrl.list_permissions(service=service))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("/entities")
async def list_entities(
    request: Request,
    response: Response,
    _user_id: Annotated[str, Depends(require_permission("permission:list"))],
) -> ResponseModel[dict[str, Any]]:
    try:
        ctrl = get_permission_controller()
        return ResponseModel(statusCode=200, data=await ctrl.list_entities())
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("/services")
async def list_services(
    request: Request,
    response: Response,
    _user_id: Annotated[str, Depends(require_permission("permission:list"))],
) -> ResponseModel[dict[str, Any]]:
    try:
        ctrl = get_permission_controller()
        return ResponseModel(statusCode=200, data=await ctrl.list_services())
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.post("/sync")
async def sync_permissions(
    request: Request,
    response: Response,
    _user_id: Annotated[str, Depends(require_permission("permission:manage"))],
) -> ResponseModel[dict[str, Any]]:
    try:
        ctrl = get_permission_controller()
        return ResponseModel(statusCode=200, data=await ctrl.sync_permissions())
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("/coverage")
async def get_permission_coverage(
    request: Request,
    response: Response,
    _user_id: Annotated[str, Depends(require_permission("permission:read"))],
) -> ResponseModel[dict[str, Any]]:
    try:
        ctrl = get_permission_controller()
        return ResponseModel(statusCode=200, data=await ctrl.get_coverage())
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@router.get("/{permission_name}")
async def get_permission(
    request: Request,
    response: Response,
    permission_name: str,
    _user_id: Annotated[str, Depends(require_permission("permission:read"))],
) -> ResponseModel[dict[str, Any]]:
    try:
        ctrl = get_permission_controller()
        return ResponseModel(statusCode=200, data=await ctrl.get_permission(permission_name))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )
