"""Onyx-shaped MCP server admin API.

Routes are declared with literal ``/api/...`` paths so that
``app._api_versioned_path`` maps them to ``{API_PREFIX}/...`` (same trick as
``AuthRoute``). They back the frontend ``apps/web/src/lib/tools/mcpService.ts``
surface, delegating to :class:`MCPProviderService`, :class:`MCPToolService`,
:class:`MCPOAuthService` and :class:`MCPCredentialService`.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.dependencies import AuthenticatedUser, require_permission, require_user
from core.logger import get_logger
from core.mcp_enums import MCPAuthType, MCPServerStatus
from models.mcp_admin import (
    MCPOAuthConnectBody,
    MCPServerCreateBody,
    MCPServerUpdateBody,
    MCPServerUpsertBody,
    ToolExecuteBody,
    ToolStatusBody,
)
from service.MCPCredentialService import MCPAuthError, MCPCredentialService
from service.MCPOAuthService import MCPOAuthService
from service.MCPProviderService import MCPProviderService
from service.MCPToolService import MCPToolService

logger = get_logger(__name__)

router = APIRouter(tags=["mcp-admin"])

_VALID_STATUSES = {s.value for s in MCPServerStatus}

# The provider service / DB persist transport in lower-case, distinct from the
# upper-case ``MCPTransport`` vocabulary the request models normalize to.
_TRANSPORT_STREAMABLE_HTTP = "streamable_http"
_TRANSPORT_SSE = "sse"


# -- service seams (monkeypatched in tests) ------------------------------- #


def _provider_service() -> MCPProviderService:
    return MCPProviderService.get_instance()


def _tool_service() -> MCPToolService:
    return MCPToolService.get_instance()


def _oauth_service() -> MCPOAuthService:
    return MCPOAuthService.get_instance()


def _credential_service() -> MCPCredentialService:
    return MCPCredentialService.get_instance()


async def _require_provider_by_int_id(int_id: int) -> dict[str, Any]:
    provider = await _provider_service().get_by_int_id(int_id)
    if not provider:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="mcp server not found")
    return provider


# -- list / read ------------------------------------------------------- #


@router.get("/api/admin/mcp/servers")
async def list_mcp_servers(
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_provider:read"))],
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, Any]:
    svc = _provider_service()
    rows = await svc.list_external()
    dtos = [await svc.to_mcp_server_dto(r, user_id=user.user_id) for r in rows]
    return {"mcp_servers": [svc.builtin_server_dto(), *dtos]}


@router.get("/api/admin/mcp/servers/{int_id}")
async def get_mcp_server(
    int_id: int,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_provider:read"))],
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, Any]:
    provider = await _require_provider_by_int_id(int_id)
    return await _provider_service().to_mcp_server_dto(
        provider, user_id=user.user_id, include_credentials=True
    )


# -- create / update / delete -------------------------------------- #


@router.post("/api/admin/mcp/server")
async def create_mcp_server(
    body: MCPServerCreateBody,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_provider:create"))],
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, Any]:
    svc = _provider_service()
    provider = await svc.create_provider(
        name=body.name,
        type="external",
        url=body.server_url,
        transport=_TRANSPORT_STREAMABLE_HTTP,
        description=body.description or "",
        auth_type=MCPAuthType.NONE.value,
        server_status=MCPServerStatus.CREATED.value,
        owner_email=user.email,
    )
    return await svc.to_mcp_server_dto(provider, user_id=user.user_id)


@router.patch("/api/admin/mcp/server/{int_id}")
async def update_mcp_server(
    int_id: int,
    body: MCPServerUpdateBody,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_provider:update"))],
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, Any]:
    provider = await _require_provider_by_int_id(int_id)
    svc = _provider_service()
    updates: dict[str, Any] = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.description is not None:
        updates["description"] = body.description
    if body.server_url is not None:
        updates["url"] = body.server_url
    updated = await svc.update_provider(provider["id"], **updates) if updates else provider
    return await svc.to_mcp_server_dto(updated or provider, user_id=user.user_id)


@router.delete("/api/admin/mcp/server/{int_id}")
async def delete_mcp_server(
    int_id: int,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_provider:delete"))],
) -> dict[str, str]:
    provider = await _require_provider_by_int_id(int_id)
    await _tool_service().delete_tools_by_provider(provider["id"])
    await _provider_service().delete_provider(provider["id"])
    return {"status": "ok"}


@router.patch("/api/admin/mcp/server/{int_id}/status")
async def set_mcp_server_status(
    int_id: int,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_provider:update"))],
    status_value: Annotated[str, Query(alias="status")],
) -> dict[str, str]:
    if status_value not in _VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid status {status_value!r}",
        )
    provider = await _require_provider_by_int_id(int_id)
    await _provider_service().set_status(provider["id"], status_value)
    return {"status": status_value}


# -- tool discovery / toggle -------------------------------------- #


@router.get("/api/admin/mcp/server/{int_id}/tools/snapshots")
async def refresh_mcp_server_tools(
    int_id: int,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_provider:sync"))],
    user: Annotated[AuthenticatedUser, Depends(require_user)],
    source: str = "mcp",
) -> list[dict[str, Any]]:
    """``source=mcp`` (default) discovers tools live from the server and upserts
    them; ``source=db`` just returns the cached ``mcp_tool`` rows."""
    provider = await _require_provider_by_int_id(int_id)

    if source == "db":
        return await _tool_service().list_snapshots_for_provider(int_id)

    try:
        snapshots = await _tool_service().sync_tools_from_provider(int_id, user_id=user.user_id)
    except (RuntimeError, ValueError, MCPAuthError) as exc:
        await _provider_service().set_status(provider["id"], MCPServerStatus.DISCONNECTED.value)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await _provider_service().set_status(provider["id"], MCPServerStatus.CONNECTED.value)
    return snapshots


@router.post("/api/admin/mcp/server/{int_id}/tools/{tool_name}/execute")
async def execute_mcp_server_tool(
    int_id: int,
    tool_name: str,
    body: ToolExecuteBody,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_provider:sync"))],
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, Any]:
    try:
        return await _tool_service().execute_tool(
            int_id, tool_name, body.arguments, user_id=user.user_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/api/admin/mcp/servers/create")
async def upsert_mcp_server(
    body: MCPServerUpsertBody,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_provider:update"))],
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, Any]:
    svc = _provider_service()
    creds = _credential_service()
    transport = _TRANSPORT_SSE if body.transport == "SSE" else _TRANSPORT_STREAMABLE_HTTP

    if body.existing_server_id is not None:
        provider = await _require_provider_by_int_id(body.existing_server_id)
    else:
        provider = await svc.create_provider(
            name=body.name,
            type="external",
            url=body.server_url,
            transport=transport,
            description=body.description or "",
            owner_email=user.email,
        )

    provider = (
        await svc.update_provider(
            provider["id"],
            name=body.name,
            url=body.server_url,
            transport=transport,
            auth_type=body.auth_type,
            auth_performer=body.auth_performer,
            auth_template=body.auth_template,
        )
        or provider
    )

    if body.auth_type == "API_TOKEN" and body.auth_performer == "ADMIN" and body.api_token:
        await creds.store_admin_credentials(provider["id"], {"api_key": body.api_token})
    elif (
        body.auth_type == "API_TOKEN"
        and body.auth_performer == "PER_USER"
        and body.admin_credentials
    ):
        await creds.store_user_credentials(provider["id"], user.user_id, body.admin_credentials)
    elif body.auth_type == "OAUTH" and body.oauth_client_id:
        await creds.store_admin_credentials(
            provider["id"],
            {
                "client_id": body.oauth_client_id,
                "client_secret": body.oauth_client_secret or "",
            },
        )

    if body.auth_type == "OAUTH":
        await svc.set_status(provider["id"], "AWAITING_AUTH")

    dto = await svc.to_mcp_server_dto(provider, user_id=user.user_id)
    return {
        "server_id": provider["int_id"],
        "server_name": body.name,
        "server_url": body.server_url,
        "auth_type": body.auth_type,
        "auth_performer": body.auth_performer,
        "is_authenticated": dto["is_authenticated"],
    }


@router.post("/api/admin/mcp/oauth/connect")
async def mcp_oauth_connect(
    body: MCPOAuthConnectBody,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_provider:update"))],
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict[str, str]:
    provider = await _require_provider_by_int_id(int(body.server_id))
    try:
        oauth_url = await _oauth_service().begin(
            provider,
            user_id=user.user_id,
            return_path=body.return_path,
            include_resource_param=body.include_resource_param,
            client_id=body.oauth_client_id,
            client_secret=body.oauth_client_secret,
        )
    except MCPAuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"oauth_url": oauth_url}


@router.patch("/api/admin/tool/status")
async def set_tool_status(
    body: ToolStatusBody,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("mcp_provider:update"))],
) -> dict[str, Any]:
    updated = await _tool_service().set_tools_enabled(body.tool_ids, body.enabled)
    return {"updated_count": updated, "tool_ids": body.tool_ids}
