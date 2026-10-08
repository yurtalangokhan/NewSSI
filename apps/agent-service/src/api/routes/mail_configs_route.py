"""Mail configuration API routes."""

from __future__ import annotations

from typing import Annotated

from error_contract import ApplicationError
from error_contract.localization import render_error_message
from fastapi import APIRouter, Depends, Query, Request, Response

from api.dependencies import AuthenticatedUser, require_permission, require_user
from core.http.response_errors import request_locale, set_error_response
from core.http.response_models import ErrorModel, ResponseModel
from schemas.common import SuccessResponse
from schemas.mail_configs import (
    AvailableMailConfigResponse,
    MailConfigCreateRequest,
    MailConfigResponse,
    MailConfigTestRequest,
    MailConfigTestResponse,
    MailConfigUpdateRequest,
    MailSendRequest,
    MailSendResponse,
    PaginatedMailConfigsResponse,
    UserMailSettingsRequest,
    UserMailSettingsResponse,
    UserMailSettingsTestRequest,
)
from service.auth import mail_configs_application_service as application_service

router = APIRouter(prefix="/api/mail-configs", tags=["mail-configs"], dependencies=[Depends(require_user)])


@router.get("/available", response_model=ResponseModel[list[AvailableMailConfigResponse]])
async def list_available_mail_configs(
    request: Request, response: Response, user: Annotated[AuthenticatedUser, Depends(require_user)]
) -> ResponseModel[list[AvailableMailConfigResponse]]:
    try:
        return ResponseModel[list[AvailableMailConfigResponse]](
            data=await application_service.list_available_mail_configs(user_id=user.user_id)
        )
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/user-credentials", response_model=ResponseModel[UserMailSettingsResponse | None])
async def get_user_mail_credentials(
    request: Request, response: Response, user: Annotated[AuthenticatedUser, Depends(require_user)]
) -> ResponseModel[UserMailSettingsResponse | None]:
    try:
        return ResponseModel[UserMailSettingsResponse | None](
            data=await application_service.get_user_mail_credentials(user_id=user.user_id)
        )
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.put("/user-credentials", response_model=ResponseModel[UserMailSettingsResponse])
async def upsert_user_mail_credentials(
    request: Request,
    response: Response,
    body: UserMailSettingsRequest,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> ResponseModel[UserMailSettingsResponse]:
    try:
        return ResponseModel[UserMailSettingsResponse](
            data=await application_service.upsert_user_mail_credentials(user_id=user.user_id, body=body)
        )
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.delete("/user-credentials", response_model=ResponseModel[SuccessResponse])
async def delete_user_mail_credentials(
    request: Request, response: Response, user: Annotated[AuthenticatedUser, Depends(require_user)]
) -> ResponseModel[SuccessResponse]:
    try:
        return ResponseModel[SuccessResponse](
            data=await application_service.delete_user_mail_credentials(user_id=user.user_id)
        )
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/user-credentials/test", response_model=ResponseModel[MailConfigTestResponse])
async def test_user_mail_credentials(
    request: Request,
    response: Response,
    body: UserMailSettingsTestRequest,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> ResponseModel[MailConfigTestResponse]:
    try:
        return ResponseModel[MailConfigTestResponse](
            data=await application_service.test_user_mail_credentials(user_id=user.user_id, body=body)
        )
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("", response_model=ResponseModel[PaginatedMailConfigsResponse])
async def list_mail_configs(
    request: Request,
    response: Response,
    user: Annotated[AuthenticatedUser, Depends(require_permission("mail_config:read"))],
    search: Annotated[str | None, Query(description="Search by name, email, host, username")] = None,
    page: Annotated[int, Query(ge=1, description="Page number (1-indexed)")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 10,
) -> ResponseModel[PaginatedMailConfigsResponse]:
    try:
        return ResponseModel[PaginatedMailConfigsResponse](
            data=await application_service.list_mail_configs(
                user_id=user.user_id, search=search, page=page, page_size=page_size
            )
        )
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("", response_model=ResponseModel[MailConfigResponse])
async def create_mail_config(
    request: Request,
    response: Response,
    body: MailConfigCreateRequest,
    user: Annotated[AuthenticatedUser, Depends(require_permission("mail_config:create"))],
) -> ResponseModel[MailConfigResponse]:
    try:
        return ResponseModel[MailConfigResponse](
            data=await application_service.create_mail_config(user_id=user.user_id, body=body)
        )
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/{config_id}", response_model=ResponseModel[MailConfigResponse])
async def get_mail_config(
    request: Request,
    response: Response,
    config_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("mail_config:read"))],
) -> ResponseModel[MailConfigResponse]:
    try:
        return ResponseModel[MailConfigResponse](
            data=await application_service.get_mail_config(user_id=user.user_id, config_id=config_id)
        )
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.patch("/{config_id}", response_model=ResponseModel[MailConfigResponse])
async def update_mail_config(
    request: Request,
    response: Response,
    config_id: str,
    body: MailConfigUpdateRequest,
    user: Annotated[AuthenticatedUser, Depends(require_permission("mail_config:update"))],
) -> ResponseModel[MailConfigResponse]:
    try:
        return ResponseModel[MailConfigResponse](
            data=await application_service.update_mail_config(user_id=user.user_id, config_id=config_id, body=body)
        )
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.delete("/{config_id}", response_model=ResponseModel[SuccessResponse])
async def delete_mail_config(
    request: Request,
    response: Response,
    config_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_permission("mail_config:delete"))],
) -> ResponseModel[SuccessResponse]:
    try:
        return ResponseModel[SuccessResponse](
            data=await application_service.delete_mail_config(user_id=user.user_id, config_id=config_id)
        )
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/{config_id}/test", response_model=ResponseModel[MailConfigTestResponse])
async def test_mail_config(
    request: Request,
    response: Response,
    config_id: str,
    body: MailConfigTestRequest,
    user: Annotated[AuthenticatedUser, Depends(require_permission("mail_config:test"))],
) -> ResponseModel[MailConfigTestResponse]:
    try:
        return ResponseModel[MailConfigTestResponse](
            data=await application_service.test_mail_config(user_id=user.user_id, config_id=config_id, body=body)
        )
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/{config_id}/send", response_model=ResponseModel[MailSendResponse])
async def send_mail_with_config(
    request: Request,
    response: Response,
    config_id: str,
    body: MailSendRequest,
    user: Annotated[AuthenticatedUser, Depends(require_permission("mail_config:send"))],
) -> ResponseModel[MailSendResponse]:
    try:
        return ResponseModel[MailSendResponse](
            data=await application_service.send_mail_with_config(user_id=user.user_id, config_id=config_id, body=body)
        )
    except ApplicationError as error:
        normalize = getattr(error, "to_application_error", None)
        if callable(normalize):
            error = normalize()
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))
