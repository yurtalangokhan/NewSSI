"""Connector options and internal-only credential resolution."""

from typing import Annotated, Any

from error_contract import ApplicationError
from error_contract.localization import render_error_message
from fastapi import APIRouter, Depends, Request, Response

from api.dependencies import AuthenticatedUser, require_internal_service_identity, require_permission
from core.http.response_errors import request_locale, set_error_response
from core.http.response_models import ErrorModel, ResponseModel
from schemas.connector_tools import ConnectorOptionResponse, ConnectorResolveRequest, ConnectorResolveResponse
from service.orchestration.connector_tool_service import get_connector_tool_service
from service.orchestration.connector_tools_application_service import ConnectorToolsApplicationService

router = APIRouter(tags=["connector-tools"])
RESOLUTION_TIMEOUT_SECONDS = 15
_internal_identity = require_internal_service_identity


@router.get("/datasources/tool-options", response_model=ResponseModel[list[ConnectorOptionResponse]])
async def connector_options(
    request: Request,
    response: Response,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("datasource:read"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await ConnectorToolsApplicationService(
                connector_service=get_connector_tool_service(), timeout_seconds=RESOLUTION_TIMEOUT_SECONDS
            ).connector_options()
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/internal/connector-tools/resolve", response_model=ResponseModel[ConnectorResolveResponse])
async def resolve_connector(
    request: Request,
    body: ConnectorResolveRequest,
    response: Response,
    user_id: Annotated[str, Depends(_internal_identity)],
) -> ResponseModel[Any]:
    response.headers["Cache-Control"] = "no-store"
    try:
        return ResponseModel(
            data=await ConnectorToolsApplicationService(
                connector_service=get_connector_tool_service(), timeout_seconds=RESOLUTION_TIMEOUT_SECONDS
            ).resolve_connector(body=body, user_id=user_id)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))
