"""MCP Tool Service - manages tool definitions and syncing from providers."""

from __future__ import annotations

import logging
from typing import Any

from core.db.repositories import MCPProviderRepository, MCPToolRepository

logger = logging.getLogger(__name__)


class MCPToolService:
    """Service for managing MCP tools."""

    _instance: MCPToolService | None = None
    _tool_repo: MCPToolRepository | None = None
    _provider_repo: MCPProviderRepository | None = None

    def __init__(
        self,
        tool_repo: MCPToolRepository | None = None,
        provider_repo: MCPProviderRepository | None = None,
    ):
        self._tool_repo = tool_repo or MCPToolRepository()
        self._provider_repo = provider_repo or MCPProviderRepository()

    @classmethod
    def get_instance(cls) -> MCPToolService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def list_tools(self, include_inactive: bool = False) -> list[dict[str, Any]]:
        return await self._tool_repo.list_all(include_inactive)

    async def list_tools_by_provider(
        self,
        provider_id: str,
        include_inactive: bool = False,
    ) -> list[dict[str, Any]]:
        return await self._tool_repo.list_by_provider(provider_id, include_inactive)

    async def get_tool(self, tool_id: str) -> dict[str, Any] | None:
        return await self._tool_repo.get_by_id(tool_id)

    async def get_tool_by_name(
        self,
        name: str,
        provider_id: str | None = None,
    ) -> dict[str, Any] | None:
        return await self._tool_repo.get_by_name(name, provider_id)

    async def list_categories(self) -> list[str]:
        return await self._tool_repo.list_categories()

    async def get_tools_by_category(self, category: str) -> list[dict[str, Any]]:
        return await self._tool_repo.get_by_category(category)

    async def sync_tools_from_provider(self, provider_id: str) -> int:
        provider = await self._provider_repo.get_by_id(provider_id)
        if not provider:
            raise ValueError(f"Provider {provider_id} not found")

        if not provider.get("url"):
            raise ValueError(f"Provider {provider_id} has no URL")

        tools = await self._fetch_tools_from_mcp(provider["url"])
        return await self._tool_repo.bulk_upsert(provider_id, tools)

    async def _fetch_tools_from_mcp(self, mcp_url: str) -> list[dict[str, Any]]:
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    mcp_url,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/list",
                    },
                    timeout=30.0,
                )
                if response.status_code == 200:
                    data = response.json()
                    tools = data.get("result", {}).get("tools", [])
                    return self._normalize_tools(tools)
                else:
                    logger.warning(f"MCP list tools failed: {response.status_code}")
                    return []
        except Exception as e:
            logger.warning(f"Failed to fetch tools from MCP: {e}")
            return []

    def _normalize_tools(self, mcp_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized = []
        for tool in mcp_tools:
            input_schema = tool.get("inputSchema") or tool.get("input_schema", {})
            category = None
            tags = []
            description = tool.get("description", "")

            if "[category:" in description:
                try:
                    cat_start = description.find("[category:") + len("[category:")
                    cat_end = description.find("]", cat_start)
                    if cat_end > cat_start:
                        category = description[cat_start:cat_end]
                except Exception:
                    pass

            if "[category_label:" in description:
                try:
                    label_start = description.find("[category_label:") + len("[category_label:")
                    label_end = description.find("]", label_start)
                    if label_end > label_start:
                        label = description[label_start:label_end]
                        tags.append(label)
                except Exception:
                    pass

            normalized.append(
                {
                    "name": tool.get("name", ""),
                    "description": description.split("[category:")[0]
                    .split("[category_label:")[0]
                    .strip(),
                    "input_schema": input_schema,
                    "metadata": {
                        "original": tool,
                    },
                    "category": category,
                    "tags": tags,
                }
            )
        return normalized

    async def sync_all_providers(self) -> dict[str, int]:
        providers = await self._provider_repo.list_all(include_inactive=False)
        results = {}
        for provider in providers:
            if provider.get("is_active") and provider.get("url"):
                try:
                    count = await self.sync_tools_from_provider(provider["id"])
                    results[provider["name"]] = count
                except Exception as e:
                    logger.warning(f"Failed to sync provider {provider['name']}: {e}")
                    results[provider["name"]] = 0
        return results

    async def create_tool(
        self,
        provider_id: str,
        name: str,
        description: str = "",
        input_schema: dict[str, Any] | None = None,
        category: str | None = None,
    ) -> dict[str, Any]:
        return await self._tool_repo.create(
            provider_id=provider_id,
            name=name,
            description=description,
            input_schema=input_schema,
            category=category,
        )

    async def delete_tool(self, tool_id: str) -> bool:
        return await self._tool_repo.delete(tool_id)

    async def delete_tools_by_provider(self, provider_id: str) -> int:
        return await self._tool_repo.delete_by_provider(provider_id)
