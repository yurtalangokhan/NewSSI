"""Per-user connector configurations, for other services only.

Every route here requires ``X-Internal-Service-Token``. A gateway identity is
not accepted, not even the owner's: the read returns decrypted source
credentials, and the only caller with a reason to hold them is the service
that runs the sync (agent-service).
"""

from typing import Any
import uuid

from error_contract import ApplicationError, render_error_message
from fastapi import APIRouter, Depends, Request, Response

from src.api.dependencies import require_internal_service_token
from src.controller import get_user_connector_config_controller
from src.core.response_errors import request_locale, set_error_response
from src.core.response_models import ErrorModel, ResponseModel
from src.schema.connector_configs import (
    ConnectorConfigCreate,
    ConnectorConfigDetail,
    ConnectorConfigMeta,
    ConnectorConfigUpdate,
)

internal_router = APIRouter(
    prefix="/internal/users",
    tags=["connector-configs"],
    dependencies=[Depends(require_internal_service_token)],
)


@internal_router.get("/{user_id}/connector-configs")
async def list_connector_configs(
    request: Request,
    response: Response,
    user_id: uuid.UUID,
) -> ResponseModel[list[ConnectorConfigMeta]]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_user_connector_config_controller().list_configs(user_id),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@internal_router.post("/{user_id}/connector-configs", status_code=201)
async def create_connector_config(
    request: Request,
    response: Response,
    user_id: uuid.UUID,
    body: ConnectorConfigCreate,
) -> ResponseModel[ConnectorConfigMeta]:
    try:
        return ResponseModel(
            statusCode=201,
            data=await get_user_connector_config_controller().create_config(
                user_id, body.connector_name, body.name, body.config
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


@internal_router.get("/{user_id}/connector-configs/{config_id}")
async def get_connector_config(
    request: Request,
    response: Response,
    user_id: uuid.UUID,
    config_id: uuid.UUID,
) -> ResponseModel[ConnectorConfigDetail]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_user_connector_config_controller().get_config(user_id, config_id),
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )


@internal_router.put("/{user_id}/connector-configs/{config_id}")
async def update_connector_config(
    request: Request,
    response: Response,
    user_id: uuid.UUID,
    config_id: uuid.UUID,
    body: ConnectorConfigUpdate,
) -> ResponseModel[ConnectorConfigMeta]:
    try:
        return ResponseModel(
            statusCode=200,
            data=await get_user_connector_config_controller().update_config(
                user_id, config_id, name=body.name, config=body.config
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


@internal_router.delete("/{user_id}/connector-configs/{config_id}", status_code=200)
async def delete_connector_config(
    request: Request,
    response: Response,
    user_id: uuid.UUID,
    config_id: uuid.UUID,
) -> ResponseModel[Any]:
    try:
        await get_user_connector_config_controller().delete_config(user_id, config_id)
        return ResponseModel(statusCode=200)
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(
            statusCode=error.status_code,
            message=message,
            error=ErrorModel.from_error(error, message),
        )
