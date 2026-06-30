"""MCP Tool routes."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import AuthenticatedUser, require_permission, require_user
from service.MCPToolService import MCPToolService

router = APIRouter(
    prefix="/mcp-tools",
    tags=["mcp-tools"],
    dependencies=[Depends(require_user)],
)


def _get_service() -> MCPToolService:
    return MCPToolService.get_instance()


@router.get("")
async def list_tools(
    service: MCPToolService = Depends(_get_service),
    include_inactive: bool = False,
    _user: AuthenticatedUser = Depends(require_permission("mcp_tool:read")),
) -> list[dict[str, Any]]:
    return await service.list_tools(include_inactive)


@router.get("/available")
async def list_available_tools(
    service: MCPToolService = Depends(_get_service),
    _user: AuthenticatedUser = Depends(require_permission("mcp_tool:read")),
) -> list[dict[str, Any]]:
    tools = await service.list_tools(include_inactive=False)
    categories = await service.list_categories()
    return {
        "tools": tools,
        "categories": categories,
        "total": len(tools),
    }


@router.get("/categories")
async def list_categories(
    service: MCPToolService = Depends(_get_service),
    _user: AuthenticatedUser = Depends(require_permission("mcp_tool:read")),
) -> list[str]:
    return await service.list_categories()


@router.get("/categories/{category}")
async def get_tools_by_category(
    category: str,
    service: MCPToolService = Depends(_get_service),
    _user: AuthenticatedUser = Depends(require_permission("mcp_tool:read")),
) -> list[dict[str, Any]]:
    return await service.get_tools_by_category(category)


@router.get("/{tool_id}")
async def get_tool(
    tool_id: str,
    service: MCPToolService = Depends(_get_service),
    _user: AuthenticatedUser = Depends(require_permission("mcp_tool:read")),
) -> dict[str, Any]:
    tool = await service.get_tool(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool {tool_id} not found")
    return tool


@router.get("/provider/{provider_id}")
async def list_tools_by_provider(
    provider_id: str,
    service: MCPToolService = Depends(_get_service),
    include_inactive: bool = False,
    _user: AuthenticatedUser = Depends(require_permission("mcp_tool:read")),
) -> list[dict[str, Any]]:
    return await service.list_tools_by_provider(provider_id, include_inactive)


@router.post("/sync")
async def sync_all_tools(
    service: MCPToolService = Depends(_get_service),
    _user: AuthenticatedUser = Depends(require_permission("mcp_tool:sync")),
) -> dict[str, int]:
    return await service.sync_all_providers()


@router.post("/provider/{provider_id}/sync")
async def sync_provider_tools(
    provider_id: str,
    service: MCPToolService = Depends(_get_service),
    _user: AuthenticatedUser = Depends(require_permission("mcp_tool:sync")),
) -> dict[str, Any]:
    count = await service.sync_tools_from_provider(provider_id)
    return {"provider_id": provider_id, "tools_synced": count}


@router.delete("/{tool_id}")
async def delete_tool(
    tool_id: str,
    service: MCPToolService = Depends(_get_service),
    _user: AuthenticatedUser = Depends(require_permission("mcp_tool:sync")),
) -> dict[str, Any]:
    deleted = await service.delete_tool(tool_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Tool {tool_id} not found")
    return {"status": "ok", "tool_id": tool_id}
