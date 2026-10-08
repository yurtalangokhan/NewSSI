"""
Sync Schedule API Routes.

CRUD endpoints for the cron schedules the connector scheduler runs
datasource syncs on.
"""

from __future__ import annotations

from typing import Annotated

from error_contract import ApplicationError
from error_contract.localization import render_error_message
from fastapi import APIRouter, Depends, Request, Response

from api.dependencies import AuthenticatedUser, require_permission, require_user
from core.http.response_errors import request_locale, set_error_response
from core.http.response_models import ErrorModel, ResponseModel
from schemas.schedules import (
    ScheduleRunStatus,
    SyncScheduleDeleteResponse,
    SyncScheduleInput,
    SyncScheduleListItem,
    SyncScheduleResponse,
    SyncScheduleUpdate,
)
from service.runtime import schedule_application_service as application_service

router = APIRouter(tags=["sync-schedules"], dependencies=[Depends(require_user)])


@router.get("/datasources/schedules", response_model=ResponseModel[list[SyncScheduleListItem]])
async def list_all_schedules(
    request: Request,
    response: Response,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("schedule:read"))],
) -> ResponseModel[list[SyncScheduleListItem]]:
    try:
        return ResponseModel[list[SyncScheduleListItem]](data=await application_service.list_all_schedules())
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/datasources/{datasource_id}/schedule", response_model=ResponseModel[SyncScheduleResponse])
async def create_schedule(
    request: Request,
    response: Response,
    datasource_id: str,
    body: SyncScheduleInput,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("schedule:create"))],
) -> ResponseModel[SyncScheduleResponse]:
    try:
        return ResponseModel[SyncScheduleResponse](
            data=await application_service.create_schedule(datasource_id=datasource_id, body=body)
        )
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/datasources/{datasource_id}/schedule", response_model=ResponseModel[SyncScheduleResponse])
async def get_schedule(
    request: Request,
    response: Response,
    datasource_id: str,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("schedule:read"))],
) -> ResponseModel[SyncScheduleResponse]:
    try:
        return ResponseModel[SyncScheduleResponse](
            data=await application_service.get_schedule(datasource_id=datasource_id)
        )
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.put("/datasources/{datasource_id}/schedule", response_model=ResponseModel[SyncScheduleResponse])
async def update_schedule(
    request: Request,
    response: Response,
    datasource_id: str,
    body: SyncScheduleUpdate,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("schedule:update"))],
) -> ResponseModel[SyncScheduleResponse]:
    try:
        return ResponseModel[SyncScheduleResponse](
            data=await application_service.update_schedule(datasource_id=datasource_id, body=body)
        )
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.delete("/datasources/{datasource_id}/schedule", response_model=ResponseModel[SyncScheduleDeleteResponse])
async def delete_schedule(
    request: Request,
    response: Response,
    datasource_id: str,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("schedule:delete"))],
) -> ResponseModel[SyncScheduleDeleteResponse]:
    try:
        return ResponseModel[SyncScheduleDeleteResponse](
            data=await application_service.delete_schedule(datasource_id=datasource_id)
        )
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/datasources/{datasource_id}/schedule/status", response_model=ResponseModel[ScheduleRunStatus])
async def get_schedule_run_status(
    request: Request,
    response: Response,
    datasource_id: str,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("schedule:read"))],
) -> ResponseModel[ScheduleRunStatus]:
    try:
        return ResponseModel[ScheduleRunStatus](
            data=await application_service.get_schedule_run_status(datasource_id=datasource_id)
        )
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))
