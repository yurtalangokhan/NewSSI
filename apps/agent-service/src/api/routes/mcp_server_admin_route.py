"""Atlas-shaped MCP server admin API.

Routes are declared with literal ``/api/...`` paths so that
``app._api_versioned_path`` maps them to ``{API_PREFIX}/...``. They back the frontend ``apps/web/src/lib/tools/mcpService.ts``
surface, delegating to :class:`MCPProviderService`, :class:`MCPToolService`,
:class:`MCPOAuthService` and :class:`MCPCredentialService`.
"""

from __future__ import annotations

from typing import Annotated, Any

from error_contract import ApplicationError
from error_contract.localization import render_error_message
from fastapi import APIRouter, Depends, Query, Request, Response

from api.dependencies import AuthenticatedUser, require_permission, require_user
from core.http.response_errors import request_locale, set_error_response
from core.http.response_models import ErrorModel, ResponseModel
from core.observability.logger import get_logger
from core.security.mcp.mcp_enums import MCPServerStatus
from schemas.common import StatusResponse
from schemas.mcp_admin import (
    MCPConnectBody,
    MCPOAuthConnectBody,
    MCPServerCreateBody,
    MCPServerDTO,
    MCPServersResponse,
    MCPServerUpdateBody,
    MCPServerUpsertBody,
    MCPServerValidateBody,
    MCPServerValidateResponse,
    OAuthConnectResponse,
    ToolExecuteBody,
    ToolExecuteResponse,
    ToolSnapshotResponse,
    ToolStatusBody,
    ToolStatusResponse,
    UpsertMCPServerResponse,
)
from service.mcp.mcp_credential_service import MCPCredentialService
from service.mcp.mcp_oauth_service import MCPOAuthService
from service.mcp.mcp_provider_service import MCPProviderService
from service.mcp.mcp_server_admin_application_service import MCPServerAdminApplicationService
from service.mcp.mcp_tool_service import MCPToolService

logger = get_logger(__name__)
router = APIRouter(tags=["mcp-admin"])
_VALID_STATUSES = {s.value for s in MCPServerStatus}
_TRANSPORT_STREAMABLE_HTTP = "streamable_http"
_TRANSPORT_SSE = "sse"


def _provider_service() -> MCPProviderService:
    return MCPProviderService.get_instance()


def _tool_service() -> MCPToolService:
    return MCPToolService.get_instance()


def _oauth_service() -> MCPOAuthService:
    return MCPOAuthService.get_instance()


def _credential_service() -> MCPCredentialService:
    return MCPCredentialService.get_instance()


@router.get("/api/admin/mcp/servers", response_model=ResponseModel[MCPServersResponse])
async def list_mcp_servers(
    request: Request,
    response: Response,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_provider:read"))],
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await MCPServerAdminApplicationService(
                provider_service=_provider_service,
                tool_service=_tool_service,
                oauth_service=_oauth_service,
                credential_service=_credential_service,
            ).list_mcp_servers(user=user)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/api/admin/mcp/servers/{server_id}", response_model=ResponseModel[MCPServerDTO])
async def get_mcp_server(
    request: Request,
    response: Response,
    server_id: str,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_provider:read"))],
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await MCPServerAdminApplicationService(
                provider_service=_provider_service,
                tool_service=_tool_service,
                oauth_service=_oauth_service,
                credential_service=_credential_service,
            ).get_mcp_server(server_id=server_id, user=user)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/api/admin/mcp/server", response_model=ResponseModel[MCPServerDTO])
async def create_mcp_server(
    request: Request,
    response: Response,
    body: MCPServerCreateBody,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_provider:create"))],
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await MCPServerAdminApplicationService(
                provider_service=_provider_service,
                tool_service=_tool_service,
                oauth_service=_oauth_service,
                credential_service=_credential_service,
            ).create_mcp_server(body=body, user=user)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/api/admin/mcp/server/validate", response_model=ResponseModel[MCPServerValidateResponse])
async def validate_mcp_server(
    request: Request,
    response: Response,
    body: MCPServerValidateBody,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_provider:create"))],
) -> ResponseModel[Any]:
    """Probe a URL as MCP without persisting it (backs the admin Verify button)."""
    try:
        return ResponseModel(
            data=await MCPServerAdminApplicationService(
                provider_service=_provider_service,
                tool_service=_tool_service,
                oauth_service=_oauth_service,
                credential_service=_credential_service,
            ).validate_mcp_server(body=body)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.patch("/api/admin/mcp/server/{server_id}", response_model=ResponseModel[MCPServerDTO])
async def update_mcp_server(
    request: Request,
    response: Response,
    server_id: str,
    body: MCPServerUpdateBody,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_provider:update"))],
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await MCPServerAdminApplicationService(
                provider_service=_provider_service,
                tool_service=_tool_service,
                oauth_service=_oauth_service,
                credential_service=_credential_service,
            ).update_mcp_server(server_id=server_id, body=body, user=user)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.delete("/api/admin/mcp/server/{server_id}", response_model=ResponseModel[StatusResponse])
async def delete_mcp_server(
    request: Request,
    response: Response,
    server_id: str,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_provider:delete"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await MCPServerAdminApplicationService(
                provider_service=_provider_service,
                tool_service=_tool_service,
                oauth_service=_oauth_service,
                credential_service=_credential_service,
            ).delete_mcp_server(server_id=server_id)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.patch("/api/admin/mcp/server/{server_id}/status", response_model=ResponseModel[StatusResponse])
async def set_mcp_server_status(
    request: Request,
    response: Response,
    server_id: str,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_provider:update"))],
    status_value: Annotated[str, Query(alias="status")],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await MCPServerAdminApplicationService(
                provider_service=_provider_service,
                tool_service=_tool_service,
                oauth_service=_oauth_service,
                credential_service=_credential_service,
            ).set_mcp_server_status(server_id=server_id, status_value=status_value)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get(
    "/api/admin/mcp/server/{server_id}/tools/snapshots", response_model=ResponseModel[list[ToolSnapshotResponse]]
)
async def refresh_mcp_server_tools(
    request: Request,
    response: Response,
    server_id: str,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_provider:sync"))],
    user: Annotated[AuthenticatedUser, Depends(require_user)],
    source: str = "mcp",
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await MCPServerAdminApplicationService(
                provider_service=_provider_service,
                tool_service=_tool_service,
                oauth_service=_oauth_service,
                credential_service=_credential_service,
            ).refresh_mcp_server_tools(server_id=server_id, user=user, source=source)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.get("/api/admin/mcp/servers/{server_id}/tools", response_model=ResponseModel[list[ToolSnapshotResponse]])
async def list_cached_mcp_server_tools(
    request: Request,
    response: Response,
    server_id: str,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_tool:read"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await MCPServerAdminApplicationService(
                provider_service=_provider_service,
                tool_service=_tool_service,
                oauth_service=_oauth_service,
                credential_service=_credential_service,
            ).list_cached_tools(server_id=server_id)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post(
    "/api/admin/mcp/server/{server_id}/tools/{tool_name}/execute", response_model=ResponseModel[ToolExecuteResponse]
)
async def execute_mcp_server_tool(
    request: Request,
    response: Response,
    server_id: str,
    tool_name: str,
    body: ToolExecuteBody,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_provider:sync"))],
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await MCPServerAdminApplicationService(
                provider_service=_provider_service,
                tool_service=_tool_service,
                oauth_service=_oauth_service,
                credential_service=_credential_service,
            ).execute_mcp_server_tool(server_id=server_id, tool_name=tool_name, body=body, user=user)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/api/admin/mcp/servers/create", response_model=ResponseModel[UpsertMCPServerResponse])
async def upsert_mcp_server(
    request: Request,
    response: Response,
    body: MCPServerUpsertBody,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_provider:update"))],
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await MCPServerAdminApplicationService(
                provider_service=_provider_service,
                tool_service=_tool_service,
                oauth_service=_oauth_service,
                credential_service=_credential_service,
            ).upsert_mcp_server(body=body, user=user)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post(
    "/api/admin/mcp/servers/{server_id}/connect",
    response_model=ResponseModel[UpsertMCPServerResponse],
)
async def connect_mcp_server(
    request: Request,
    response: Response,
    server_id: str,
    body: MCPConnectBody,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_provider:connect"))],
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> ResponseModel[Any]:
    """Bind credentials to a registered provider (no url accepted, see schema)."""
    try:
        return ResponseModel(
            data=await MCPServerAdminApplicationService(
                provider_service=_provider_service,
                tool_service=_tool_service,
                oauth_service=_oauth_service,
                credential_service=_credential_service,
            ).connect_mcp_server(server_id=server_id, body=body, user=user)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.delete(
    "/api/admin/mcp/servers/{server_id}/connect",
    response_model=ResponseModel[StatusResponse],
)
async def disconnect_mcp_server(
    request: Request,
    response: Response,
    server_id: str,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_provider:connect"))],
) -> ResponseModel[Any]:
    """Unbind credentials and tools from a provider; the registration is kept."""
    try:
        return ResponseModel(
            data=await MCPServerAdminApplicationService(
                provider_service=_provider_service,
                tool_service=_tool_service,
                oauth_service=_oauth_service,
                credential_service=_credential_service,
            ).disconnect_mcp_server(server_id=server_id)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.post("/api/admin/mcp/oauth/connect", response_model=ResponseModel[OAuthConnectResponse])
async def mcp_oauth_connect(
    request: Request,
    response: Response,
    body: MCPOAuthConnectBody,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_provider:update"))],
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await MCPServerAdminApplicationService(
                provider_service=_provider_service,
                tool_service=_tool_service,
                oauth_service=_oauth_service,
                credential_service=_credential_service,
            ).mcp_oauth_connect(body=body, user=user)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))


@router.patch("/api/admin/tool/status", response_model=ResponseModel[ToolStatusResponse])
async def set_tool_status(
    request: Request,
    response: Response,
    body: ToolStatusBody,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_provider:update"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await MCPServerAdminApplicationService(
                provider_service=_provider_service,
                tool_service=_tool_service,
                oauth_service=_oauth_service,
                credential_service=_credential_service,
            ).set_tool_status(body=body)
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))
