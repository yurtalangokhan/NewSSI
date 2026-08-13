"""MCP Provider routes."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from i18n import t

from api.dependencies import require_permission, require_user
from service.MCPProviderService import MCPProviderService

router = APIRouter(
    prefix="/mcp-providers",
    tags=["mcp-providers"],
    dependencies=[Depends(require_user)],
)


def _get_service() -> MCPProviderService:
    return MCPProviderService.get_instance()


@router.get("")
async def list_providers(
    service: MCPProviderService = Depends(_get_service),
    include_inactive: bool = False,
    _user=Depends(require_permission("mcp_provider:read")),
) -> list[dict[str, Any]]:
    return await service.list_providers(include_inactive)


@router.get("/{provider_id}")
async def get_provider(
    provider_id: str,
    service: MCPProviderService = Depends(_get_service),
    _user=Depends(require_permission("mcp_provider:read")),
) -> dict[str, Any]:
    provider = await service.get_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail=t("mcp_provider.not_found", provider_id=provider_id))
    return provider


@router.post("")
async def create_provider(
    request: dict[str, Any],
    service: MCPProviderService = Depends(_get_service),
    _user=Depends(require_permission("mcp_provider:create")),
) -> dict[str, Any]:
    return await service.create_provider(
        name=request.get("name", ""),
        type=request.get("type", "external"),
        url=request.get("url"),
        transport=request.get("transport", "streamable_http"),
        config=request.get("config"),
        description=request.get("description", ""),
    )


@router.post("/{provider_id}/sync")
async def sync_provider_tools(
    provider_id: str,
    service: MCPProviderService = Depends(_get_service),
    _user=Depends(require_permission("mcp_provider:sync")),
) -> dict[str, Any]:
    from service.MCPToolService import MCPToolService

    tool_service = MCPToolService.get_instance()
    count = await tool_service.sync_tools_from_provider(provider_id)
    return {"provider_id": provider_id, "tools_synced": count}


@router.patch("/{provider_id}")
async def update_provider(
    provider_id: str,
    request: dict[str, Any],
    service: MCPProviderService = Depends(_get_service),
    _user=Depends(require_permission("mcp_provider:update")),
) -> dict[str, Any]:
    updated = await service.update_provider(provider_id, **request)
    if not updated:
        raise HTTPException(status_code=404, detail=t("mcp_provider.not_found", provider_id=provider_id))
    return updated


@router.delete("/{provider_id}")
async def delete_provider(
    provider_id: str,
    service: MCPProviderService = Depends(_get_service),
    _user=Depends(require_permission("mcp_provider:delete")),
) -> dict[str, Any]:
    deleted = await service.delete_provider(provider_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=t("mcp_provider.not_found", provider_id=provider_id))
    return {"status": "ok", "provider_id": provider_id}
