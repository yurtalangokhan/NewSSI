"""MCP Tool routes."""

from typing import Annotated, Any

from error_contract import ApplicationError
from error_contract.localization import render_error_message
from fastapi import APIRouter, Depends, Request, Response

from api.dependencies import AuthenticatedUser, require_permission, require_user
from core.http.response_errors import request_locale, set_error_response
from core.http.response_models import ErrorModel, ResponseModel
from schemas.mcp_admin import (
    AvailableToolsResponse,
    MCPToolDeleteResponse,
    MCPToolResponse,
    MCPToolSyncAllResponse,
    MCPToolSyncResponse,
)
from service.mcp.mcp_tool_service import MCPToolService
from service.mcp.mcp_tools_application_service import MCPToolsApplicationService

router = APIRouter(prefix="/mcp-tools", tags=["mcp-tools"], dependencies=[Depends(require_user)])


def _get_service() -> MCPToolService:
    return MCPToolService.get_instance()


@router.get("", response_model=ResponseModel[list[MCPToolResponse]])
async def list_tools(
    request: Request,
    response: Response,
    service: Annotated[MCPToolService, Depends(_get_service)],
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_tool:read"))],
    include_inactive: bool = False,
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await MCPToolsApplicationService().list_tools(service=service, include_inactive=include_inactive)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/available", response_model=ResponseModel[AvailableToolsResponse])
async def list_available_tools(
    request: Request,
    response: Response,
    service: Annotated[MCPToolService, Depends(_get_service)],
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_tool:read"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(data=await MCPToolsApplicationService().list_available_tools(service=service))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/categories", response_model=ResponseModel[list[str]])
async def list_categories(
    request: Request,
    response: Response,
    service: Annotated[MCPToolService, Depends(_get_service)],
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_tool:read"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(data=await MCPToolsApplicationService().list_categories(service=service))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/categories/{category}", response_model=ResponseModel[list[MCPToolResponse]])
async def get_tools_by_category(
    request: Request,
    response: Response,
    category: str,
    service: Annotated[MCPToolService, Depends(_get_service)],
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_tool:read"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await MCPToolsApplicationService().get_tools_by_category(category=category, service=service)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/{tool_id}", response_model=ResponseModel[MCPToolResponse])
async def get_tool(
    request: Request,
    response: Response,
    tool_id: str,
    service: Annotated[MCPToolService, Depends(_get_service)],
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_tool:read"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(data=await MCPToolsApplicationService().get_tool(tool_id=tool_id, service=service))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/provider/{provider_id}", response_model=ResponseModel[list[MCPToolResponse]])
async def list_tools_by_provider(
    request: Request,
    response: Response,
    provider_id: str,
    service: Annotated[MCPToolService, Depends(_get_service)],
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_tool:read"))],
    include_inactive: bool = False,
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await MCPToolsApplicationService().list_tools_by_provider(
                provider_id=provider_id, service=service, include_inactive=include_inactive
            )
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/sync", response_model=ResponseModel[MCPToolSyncAllResponse])
async def sync_all_tools(
    request: Request,
    response: Response,
    service: Annotated[MCPToolService, Depends(_get_service)],
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_tool:sync"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(data=await MCPToolsApplicationService().sync_all_tools(service=service))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/provider/{provider_id}/sync", response_model=ResponseModel[MCPToolSyncResponse])
async def sync_provider_tools(
    request: Request,
    response: Response,
    provider_id: str,
    service: Annotated[MCPToolService, Depends(_get_service)],
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_tool:sync"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await MCPToolsApplicationService().sync_provider_tools(provider_id=provider_id, service=service)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.delete("/{tool_id}", response_model=ResponseModel[MCPToolDeleteResponse])
async def delete_tool(
    request: Request,
    response: Response,
    tool_id: str,
    service: Annotated[MCPToolService, Depends(_get_service)],
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_tool:sync"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(data=await MCPToolsApplicationService().delete_tool(tool_id=tool_id, service=service))
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))
