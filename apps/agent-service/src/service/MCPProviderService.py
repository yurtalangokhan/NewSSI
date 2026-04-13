"""MCP Provider Service - manages MCP server configurations."""

from __future__ import annotations

import logging
from typing import Any

from core.db.repositories import MCPProviderRepository

logger = logging.getLogger(__name__)


class MCPProviderService:
    """Service for managing MCP providers."""

    _instance: MCPProviderService | None = None
    _repo: MCPProviderRepository | None = None

    def __init__(self, repo: MCPProviderRepository | None = None):
        self._repo = repo or MCPProviderRepository()

    @classmethod
    def get_instance(cls) -> MCPProviderService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def list_providers(self, include_inactive: bool = False) -> list[dict[str, Any]]:
        return await self._repo.list_all(include_inactive)

    async def get_provider(self, provider_id: str) -> dict[str, Any] | None:
        return await self._repo.get_by_id(provider_id)

    async def get_provider_by_name(self, name: str) -> dict[str, Any] | None:
        return await self._repo.get_by_name(name)

    async def get_builtin_provider(self) -> dict[str, Any] | None:
        return await self._repo.get_builtin()

    async def create_provider(
        self,
        name: str,
        type: str = "external",
        url: str | None = None,
        transport: str = "streamable_http",
        config: dict[str, Any] | None = None,
        description: str = "",
    ) -> dict[str, Any]:
        return await self._repo.create(
            name=name,
            type=type,
            url=url,
            transport=transport,
            config=config,
            is_builtin=False,
            description=description,
        )

    async def register_builtin_provider(
        self,
        name: str = "tool-service",
        url: str | None = None,
    ) -> dict[str, Any]:
        existing = await self._repo.get_by_name(name)
        if existing:
            return existing

        return await self._repo.create(
            name=name,
            type="builtin",
            url=url,
            transport="streamable_http",
            is_builtin=True,
            description="Built-in tool service MCP server",
        )

    async def update_provider(
        self,
        provider_id: str,
        **fields: Any,
    ) -> dict[str, Any] | None:
        return await self._repo.update(provider_id, **fields)

    async def delete_provider(self, provider_id: str) -> bool:
        return await self._repo.delete(provider_id)

    async def deactivate_provider(self, provider_id: str) -> bool:
        return await self._repo.deactivate(provider_id)

    async def initialize_builtin(
        self, default_url: str = "http://localhost:8002/mcp"
    ) -> dict[str, Any]:
        return await self.register_builtin_provider(name="tool-service", url=default_url)
