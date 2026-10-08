"""AdminMCP application use cases."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.observability.logger import get_logger
from service.mcp.mcp_admin_helpers import (
    SECRET_CONFIG_KEYS,
    VALID_STATUSES,
    encrypt_mcp_secret,
    get_tool_count,
    resolve_mcp_provider,
    server_config,
    to_mcp_server,
)
from service.mcp.mcp_provider_service import MCPProviderService
from service.mcp.mcp_tool_service import MCPToolService

logger = get_logger(__name__)
_SECRET_CONFIG_KEYS = SECRET_CONFIG_KEYS
_VALID_STATUSES = VALID_STATUSES
_server_config = server_config
_encrypt = encrypt_mcp_secret
_to_mcp_server = to_mcp_server


class AdminMCPApplicationService:
    """Framework-free application use cases for this JSON surface."""

    def __init__(self, tool_service: Callable[[], MCPToolService]):
        self._tool_service_factory = tool_service

    @property
    def tool_service(self) -> MCPToolService:
        return self._tool_service_factory()

    async def _tool_count(self, provider_id: str) -> int:
        return await get_tool_count(self.tool_service, provider_id)

    async def _resolve_provider(self, server_id: str, service: MCPProviderService) -> dict[str, Any]:
        return await resolve_mcp_provider(service, server_id)

    async def get_mcp_server(self, server_id: str, service: MCPProviderService) -> dict[str, Any]:
        provider = await self._resolve_provider(server_id, service)
        return _to_mcp_server(provider, await self._tool_count(provider["id"]))
