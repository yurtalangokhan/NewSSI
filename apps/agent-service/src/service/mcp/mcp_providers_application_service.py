"""MCPProviders application use cases."""

from typing import Any

from error_contract import NotFoundError

from service.mcp.mcp_provider_service import MCPProviderService


class MCPProvidersApplicationService:
    """Framework-free application use cases for this JSON surface."""

    async def list_providers(self, service: MCPProviderService, include_inactive: bool = False) -> list[dict[str, Any]]:
        return await service.list_providers(include_inactive)

    async def get_provider(self, provider_id: str, service: MCPProviderService) -> dict[str, Any]:
        provider = await service.get_provider(provider_id)
        if not provider:
            raise NotFoundError(message_key="mcp_provider.not_found", message_params={"provider_id": provider_id})
        return provider

    async def create_provider(self, request: dict[str, Any], service: MCPProviderService) -> dict[str, Any]:
        return await service.create_provider(
            name=request.get("name", ""),
            type=request.get("type", "external"),
            url=request.get("url"),
            transport=request.get("transport", "streamable_http"),
            config=request.get("config"),
            description=request.get("description", ""),
        )

    async def sync_provider_tools(self, provider_id: str, _service: MCPProviderService) -> dict[str, Any]:
        from service.mcp.mcp_tool_service import MCPToolService

        tool_service = MCPToolService.get_instance()
        snapshots = await tool_service.sync_tools_from_provider(provider_id)
        return {"provider_id": provider_id, "tools_synced": len(snapshots)}

    async def update_provider(
        self, provider_id: str, request: dict[str, Any], service: MCPProviderService
    ) -> dict[str, Any]:
        updated = await service.update_provider(provider_id, **request)
        if not updated:
            raise NotFoundError(message_key="mcp_provider.not_found", message_params={"provider_id": provider_id})
        return updated

    async def delete_provider(self, provider_id: str, service: MCPProviderService) -> dict[str, Any]:
        deleted = await service.delete_provider(provider_id)
        if not deleted:
            raise NotFoundError(message_key="mcp_provider.not_found", message_params={"provider_id": provider_id})
        return {"status": "ok", "provider_id": provider_id}
