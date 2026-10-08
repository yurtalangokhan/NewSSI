"""MCP Provider routes."""

from typing import Annotated, Any

from error_contract import ApplicationError
from error_contract.localization import render_error_message
from fastapi import APIRouter, Depends, Request, Response

from api.dependencies import AuthenticatedUser, require_permission, require_user
from core.http.response_errors import request_locale, set_error_response
from core.http.response_models import ErrorModel, ResponseModel
from schemas.mcp_admin import MCPProviderDeleteResponse, MCPProviderResponse, MCPToolSyncResponse
from service.mcp.mcp_provider_service import MCPProviderService
from service.mcp.mcp_providers_application_service import MCPProvidersApplicationService

router = APIRouter(prefix="/mcp-providers", tags=["mcp-providers"], dependencies=[Depends(require_user)])


def _get_service() -> MCPProviderService:
    return MCPProviderService.get_instance()


@router.get("", response_model=ResponseModel[list[MCPProviderResponse]])
async def list_providers(
    request: Request,
    response: Response,
    service: Annotated[MCPProviderService, Depends(_get_service)],
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_provider:read"))],
    include_inactive: bool = False,
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await MCPProvidersApplicationService().list_providers(
                service=service, include_inactive=include_inactive
            )
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/{provider_id}", response_model=ResponseModel[MCPProviderResponse])
async def get_provider(
    request: Request,
    response: Response,
    provider_id: str,
    service: Annotated[MCPProviderService, Depends(_get_service)],
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_provider:read"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await MCPProvidersApplicationService().get_provider(provider_id=provider_id, service=service)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("", response_model=ResponseModel[MCPProviderResponse])
async def create_provider(
    http_request: Request,
    response: Response,
    request: dict[str, Any],
    service: Annotated[MCPProviderService, Depends(_get_service)],
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_provider:create"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await MCPProvidersApplicationService().create_provider(request=request, service=service)
        )
    except ApplicationError as error:
        set_error_response(response, error, http_request)
        message = render_error_message(error, locale=request_locale(http_request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/{provider_id}/sync", response_model=ResponseModel[MCPToolSyncResponse])
async def sync_provider_tools(
    request: Request,
    response: Response,
    provider_id: str,
    service: Annotated[MCPProviderService, Depends(_get_service)],
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_provider:sync"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await MCPProvidersApplicationService().sync_provider_tools(provider_id=provider_id, service=service)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.patch("/{provider_id}", response_model=ResponseModel[MCPProviderResponse])
async def update_provider(
    http_request: Request,
    response: Response,
    provider_id: str,
    request: dict[str, Any],
    service: Annotated[MCPProviderService, Depends(_get_service)],
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_provider:update"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await MCPProvidersApplicationService().update_provider(
                provider_id=provider_id, request=request, service=service
            )
        )
    except ApplicationError as error:
        set_error_response(response, error, http_request)
        message = render_error_message(error, locale=request_locale(http_request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.delete("/{provider_id}", response_model=ResponseModel[MCPProviderDeleteResponse])
async def delete_provider(
    request: Request,
    response: Response,
    provider_id: str,
    service: Annotated[MCPProviderService, Depends(_get_service)],
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_provider:delete"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await MCPProvidersApplicationService().delete_provider(provider_id=provider_id, service=service)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))
