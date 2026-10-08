"""MCPTools application use cases."""

from typing import Any

from error_contract import NotFoundError

from service.mcp.mcp_tool_service import MCPToolService


class MCPToolsApplicationService:
    """Framework-free application use cases for this JSON surface."""

    async def list_tools(self, service: MCPToolService, include_inactive: bool = False) -> list[dict[str, Any]]:
        return await service.list_tools(include_inactive)

    async def list_available_tools(self, service: MCPToolService) -> dict[str, Any]:
        tools = await service.list_tools(include_inactive=False)
        categories = await service.list_categories()
        return {"tools": tools, "categories": categories, "total": len(tools)}

    async def list_categories(self, service: MCPToolService) -> list[str]:
        return await service.list_categories()

    async def get_tools_by_category(self, category: str, service: MCPToolService) -> list[dict[str, Any]]:
        return await service.get_tools_by_category(category)

    async def get_tool(self, tool_id: str, service: MCPToolService) -> dict[str, Any]:
        tool = await service.get_tool(tool_id)
        if not tool:
            raise NotFoundError(message_key="tool.not_found", message_params={"tool_id": tool_id})
        return tool

    async def list_tools_by_provider(
        self, provider_id: str, service: MCPToolService, include_inactive: bool = False
    ) -> list[dict[str, Any]]:
        return await service.list_tools_by_provider(provider_id, include_inactive)

    async def sync_all_tools(self, service: MCPToolService) -> dict[str, int]:
        return await service.sync_all_providers()

    async def sync_provider_tools(self, provider_id: str, service: MCPToolService) -> dict[str, Any]:
        snapshots = await service.sync_tools_from_provider(provider_id)
        return {"provider_id": provider_id, "tools_synced": len(snapshots)}

    async def delete_tool(self, tool_id: str, service: MCPToolService) -> dict[str, Any]:
        deleted = await service.delete_tool(tool_id)
        if not deleted:
            raise NotFoundError(message_key="tool.not_found", message_params={"tool_id": tool_id})
        return {"status": "ok", "tool_id": tool_id}
