"""MCP Provider Service - manages MCP server configurations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from core.observability.logger import get_logger
from core.security.mcp.mcp_ssrf_guard import validate_mcp_server_url
from core.security.mcp.mcp_url_policy import default_mcp_url
from infrastructure.db.persistence_gateway import mcp_provider_repository, mcp_tool_repository
from schemas.mcp_admin import MCPProviderEntity, MCPServerDTO
from service.mcp.mcp_credential_service import MCPCredentialService

if TYPE_CHECKING:
    # Type only: the repository itself comes from the gateway at
    # runtime, so the class is never reachable here.
    from infrastructure.db.repositories import (
        MCPProviderRepository,
        MCPToolRepository,
    )


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
        self._repo = repo or mcp_provider_repository()
        self._tool_repo = tool_repo or mcp_tool_repository()

    @classmethod
    def get_instance(cls) -> MCPProviderService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def list_providers(self, include_inactive: bool = False) -> list[MCPProviderEntity]:
        rows = await self._repo.list_all(include_inactive)
        return [MCPProviderEntity.model_validate(r) if not isinstance(r, MCPProviderEntity) else r for r in rows]

    async def get_provider(self, provider_id: str) -> MCPProviderEntity | None:
        row = await self._repo.get_by_id(provider_id)
        return MCPProviderEntity.model_validate(row) if row else None

    async def get_provider_by_name(self, name: str) -> MCPProviderEntity | None:
        row = await self._repo.get_by_name(name)
        return MCPProviderEntity.model_validate(row) if row else None

    async def get_builtin_provider(self) -> MCPProviderEntity | None:
        row = await self._repo.get_builtin()
        return MCPProviderEntity.model_validate(row) if row else None

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
        # Every admin-created provider is external (the builtin tools-service
        # is seeded through ensure_builtin, which bypasses this method), so an
        # admin-supplied URL is always subject to the SSRF guard.
        if url:
            await validate_mcp_server_url(url)
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
        if fields.get("url"):
            existing = await self._repo.get_by_id(provider_id)
            # The platform's own tools-service is internal by definition; only
            # federated external servers are held to the public-address rule.
            if not (existing or {}).get("is_builtin"):
                await validate_mcp_server_url(fields["url"])
        return await self._repo.update(provider_id, **fields)

    async def list_external(self) -> list[MCPProviderEntity]:
        rows = await self._repo.list_all(include_inactive=False)
        return [MCPProviderEntity.model_validate(r) for r in rows if r.get("type") == "external"]

    async def get_by_int_id(self, int_id: int) -> MCPProviderEntity | None:
        row = await self._repo.get_by_int_id(int_id)
        return MCPProviderEntity.model_validate(row) if row else None

    async def resolve_provider(self, server_id: str) -> MCPProviderEntity | None:
        """Look a provider up by either id the admin API accepts.

        The frontend holds ``int_id`` — that is what ``to_mcp_server_dto``
        publishes as ``id`` — while API clients address providers by UUID. Both
        reach the same row here, so every endpoint on a provider path reads the
        same id space.
        """
        if server_id.isdigit():
            return await self.get_by_int_id(int(server_id))
        return await self.get_provider(server_id)

    async def set_status(self, provider_id: str, status: str) -> bool:
        return await self._repo.set_status(provider_id, status)

    async def delete_provider(self, provider_id: str) -> bool:
        return await self._repo.delete(provider_id)

    async def _tool_count(self, provider_id: str) -> int:
        rows = await self._tool_repo.list_by_provider(provider_id, include_inactive=False)
        return len(rows)

    async def to_mcp_server_dto(
        self,
        row: dict[str, Any] | MCPProviderEntity,
        *,
        user_id: str | None,
        include_credentials: bool = False,
    ) -> MCPServerDTO:
        """Map a provider row to the Atlas frontend ``MCPServer`` shape."""
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

        admin_creds = None
        user_creds = None
        if include_credentials:
            admin_creds = creds.masked_credentials(await creds.get_credentials(row["id"], None))
            user_creds = creds.masked_credentials(await creds.get_credentials(row["id"], user_id))

        return MCPServerDTO(
            id=row["int_id"],
            name=row["name"],
            description=row.get("description") or "",
            server_url=row.get("url") or "",
            owner=row.get("owner_email") or "system",
            transport=row.get("transport"),
            auth_type=auth_type,
            auth_performer=auth_performer,
            is_authenticated=is_authenticated,
            user_authenticated=user_authenticated,
            auth_template=row.get("auth_template"),
            status=row.get("server_status", "CREATED"),
            tool_count=await self._tool_count(row["id"]),
            last_refreshed_at=row.get("time_updated"),
            admin_credentials=admin_creds,
            user_credentials=user_creds,
        )

    @staticmethod
    def builtin_server_dto() -> MCPServerDTO:
        """Synthetic entry for the always-present built-in tools server (id 1)."""
        return MCPServerDTO(
            id=BUILTIN_SERVER_ID,
            name="Built-in Tools",
            description="Built-in tools service",
            server_url=default_mcp_url(),
            owner="system",
            transport="streamable_http",
            auth_type="NONE",
            auth_performer=None,
            is_authenticated=True,
            user_authenticated=True,
            auth_template=None,
            status="CONNECTED",
            tool_count=0,
            last_refreshed_at=datetime.now(UTC).isoformat(),
        )

    async def deactivate_provider(self, provider_id: str) -> bool:
        return await self._repo.deactivate(provider_id)

    async def initialize_builtin(self, default_url: str | None = None) -> dict[str, Any]:
        url = default_url or default_mcp_url()
        return await self.register_builtin_provider(name="tool-service", url=url)
