"""Admin MCP server routes.

Serves the ``/api/admin/mcp/*`` surface the web admin panel
(``apps/web/src/lib/tools/mcpService.ts``) calls. Storage is the existing
``mcp_provider`` / ``mcp_tool`` tables via :class:`MCPProviderService` and
:class:`MCPToolService` — this router is an adapter that speaks the frontend's
``MCPServer`` shape, not a second store.

Two shape mismatches are handled here:

* the frontend types ``MCPServer.id`` as a ``number`` while providers are keyed
  by UUID — :func:`numeric_id_for` derives a stable 48-bit id from the UUID and
  :func:`_resolve_provider` maps it back (UUIDs are accepted on input too);
* the frontend carries auth/transport/status fields the provider table has no
  columns for — they live under the provider's ``config`` JSONB, with secrets
  encrypted and never echoed back.
"""

from __future__ import annotations

from typing import Annotated, Any

from error_contract import ApplicationError
from error_contract.localization import render_error_message
from fastapi import APIRouter, Depends, Request, Response

from api.dependencies import AuthenticatedUser, require_permission, require_user
from api.helpers.mcp_admin_helpers import (
    SECRET_CONFIG_KEYS,
    VALID_STATUSES,
    encrypt_mcp_secret,
    server_config,
    to_mcp_server,
)
from core.http.response_errors import request_locale, set_error_response
from core.http.response_models import ErrorModel, ResponseModel
from core.observability.logger import get_logger
from schemas.mcp_admin import MCPServerDTO
from service.mcp.admin_mcp_application_service import AdminMCPApplicationService
from service.mcp.mcp_provider_service import MCPProviderService
from service.mcp.mcp_tool_service import MCPToolService

logger = get_logger(__name__)
router = APIRouter(prefix="/api/admin/mcp", tags=["admin-mcp"], dependencies=[Depends(require_user)])
_SECRET_CONFIG_KEYS = SECRET_CONFIG_KEYS
_VALID_STATUSES = VALID_STATUSES
_server_config = server_config
_encrypt = encrypt_mcp_secret
_to_mcp_server = to_mcp_server


def _provider_service() -> MCPProviderService:
    return MCPProviderService.get_instance()


def _tool_service() -> MCPToolService:
    return MCPToolService.get_instance()


@router.get("/server/{server_id}", response_model=ResponseModel[MCPServerDTO])
async def get_mcp_server(
    request: Request,
    response: Response,
    server_id: str,
    service: Annotated[MCPProviderService, Depends(_provider_service)],
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_provider:read"))],
) -> ResponseModel[Any]:
    try:
        return ResponseModel(
            data=await AdminMCPApplicationService(tool_service=_tool_service).get_mcp_server(
                server_id=server_id, service=service
            )
        )
    except ApplicationError as error:
        set_error_response(response, error, request)
        message = render_error_message(error, locale=request_locale(request))
        return ResponseModel(statusCode=error.status_code, message=message, error=ErrorModel.from_error(error, message))
