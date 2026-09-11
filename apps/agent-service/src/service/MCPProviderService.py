"""MCP Provider Service - manages MCP server configurations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from core.db.repositories import MCPProviderRepository, MCPToolRepository
from core.env import env
from core.logger import get_logger
from service.MCPCredentialService import MCPCredentialService

logger = get_logger(__name__)

# The synthetic built-in tools server always occupies id 1; external providers
# start at 1000 (see migration 0042).
BUILTIN_SERVER_ID = 1


class MCPProviderService:
    """Service for managing MCP providers."""

    _instance: MCPProviderService | None = None
    _repo: MCPProviderRepository | None = None

    def __init__(
        self,
        repo: MCPProviderRepository | None = None,
        tool_repo: MCPToolRepository | None = None,
    ):
        self._repo = repo or MCPProviderRepository()
        self._tool_repo = tool_repo or MCPToolRepository()

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
        auth_type: str = "NONE",
        auth_performer: str | None = None,
        server_status: str = "CREATED",
        auth_template: dict[str, Any] | None = None,
        owner_email: str | None = None,
        oauth_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._repo.create(
            name=name,
            type=type,
            url=url,
            transport=transport,
            config=config,
            is_builtin=False,
            description=description,
            auth_type=auth_type,
            auth_performer=auth_performer,
            server_status=server_status,
            auth_template=auth_template,
            owner_email=owner_email,
            oauth_metadata=oauth_metadata,
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

    async def list_external(self) -> list[dict[str, Any]]:
        rows = await self._repo.list_all(include_inactive=False)
        return [r for r in rows if r.get("type") == "external"]

    async def get_by_int_id(self, int_id: int) -> dict[str, Any] | None:
        return await self._repo.get_by_int_id(int_id)

    async def set_status(self, provider_id: str, status: str) -> bool:
        return await self._repo.set_status(provider_id, status)

    async def delete_provider(self, provider_id: str) -> bool:
        return await self._repo.delete(provider_id)

    async def _tool_count(self, provider_id: str) -> int:
        rows = await self._tool_repo.list_by_provider(provider_id, include_inactive=False)
        return len(rows)

    async def to_mcp_server_dto(
        self,
        row: dict[str, Any],
        *,
        user_id: str | None,
        include_credentials: bool = False,
    ) -> dict[str, Any]:
        """Map a provider row to the Onyx frontend ``MCPServer`` shape."""
        auth_type = row.get("auth_type", "NONE")
        auth_performer = row.get("auth_performer")
        creds = MCPCredentialService.get_instance()

        if auth_type == "NONE":
            is_authenticated = True
            user_authenticated = True
        else:
            admin_scope = None if auth_performer == "ADMIN" else user_id
            is_authenticated = await creds.has_valid_auth(row, user_id=admin_scope)
            if auth_performer == "PER_USER":
                user_authenticated = await creds.has_valid_auth(row, user_id=user_id)
            else:
                user_authenticated = is_authenticated

        dto: dict[str, Any] = {
            "id": row["int_id"],
            "name": row["name"],
            "description": row.get("description") or "",
            "server_url": row.get("url") or "",
            "owner": row.get("owner_email") or "system",
            "transport": row.get("transport"),
            "auth_type": auth_type,
            "auth_performer": auth_performer,
            "is_authenticated": is_authenticated,
            "user_authenticated": user_authenticated,
            "auth_template": row.get("auth_template"),
            "status": row.get("server_status", "CREATED"),
            "tool_count": await self._tool_count(row["id"]),
            "last_refreshed_at": row.get("time_updated"),
        }

        if include_credentials:
            dto["admin_credentials"] = creds.masked_credentials(
                await creds.get_credentials(row["id"], None)
            )
            dto["user_credentials"] = creds.masked_credentials(
                await creds.get_credentials(row["id"], user_id)
            )

        return dto

    @staticmethod
    def builtin_server_dto() -> dict[str, Any]:
        """Synthetic entry for the always-present built-in tools server (id 1)."""
        return {
            "id": BUILTIN_SERVER_ID,
            "name": "Built-in Tools",
            "description": "Built-in tools service",
            "server_url": env.TOOLS_SERVICE_URL or env.MCP_SERVER_URL,
            "owner": "system",
            "transport": "streamable_http",
            "auth_type": "NONE",
            "auth_performer": None,
            "is_authenticated": True,
            "user_authenticated": True,
            "auth_template": None,
            "status": "CONNECTED",
            "tool_count": 0,
            "last_refreshed_at": datetime.now(UTC).isoformat(),
        }

    async def deactivate_provider(self, provider_id: str) -> bool:
        return await self._repo.deactivate(provider_id)

    async def initialize_builtin(
        self, default_url: str = "http://localhost:8003/mcp"
    ) -> dict[str, Any]:
        return await self.register_builtin_provider(name="tool-service", url=default_url)
