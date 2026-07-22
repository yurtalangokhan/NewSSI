"""Auth-adjacent controller for token-backed agent-service routes."""

import os
from typing import Any

from fastapi import Request

from controller.base import BaseController
from service.AuthService import AuthenticatedUser, get_auth_service


class AuthController(BaseController):
    """Controller for user context endpoints that consume existing tokens."""

    def __init__(self):
        self._auth_service = get_auth_service()

    async def get_current_user(self, request: Request, user: AuthenticatedUser) -> dict[str, Any]:
        return await self._auth_service.get_current_user(request=request, user=user)

    async def get_settings(self) -> dict[str, Any]:
        return {
            "auto_scroll": True,
            "application_status": "active",
            "gpu_enabled": False,
            "maximum_chat_retention_days": None,
            "notifications": [],
            "needs_reindexing": False,
            "anonymous_user_enabled": False,
            "invite_only_enabled": False,
            "deep_research_enabled": True,
            "temperature_override_enabled": True,
            "query_history_type": "normal",
        }

    async def get_enterprise_settings(self) -> dict[str, Any]:
        return {"application_name": "Agentic AI", "use_custom_logo": False}

    async def health_check(self) -> dict[str, Any]:
        return {"status": "ok"}

    async def get_mcp_servers(self) -> dict[str, Any]:
        mcp_servers = []
        tools_service_url = (
            os.getenv("TOOLS_SERVICE_URL") or os.getenv("MCP_SERVER_URL") or "http://localhost:8003"
        )

        if tools_service_url:
            from datetime import UTC, datetime

            mcp_servers.append(
                {
                    "id": 1,
                    "name": "Built-in Tools",
                    "description": "Built-in tools service",
                    "server_url": tools_service_url,
                    "owner": "system",
                    "is_authenticated": True,
                    "status": "CONNECTED",
                    "tool_count": 0,
                    "last_refreshed_at": datetime.now(UTC).isoformat(),
                }
            )

        return {"mcp_servers": mcp_servers}


_auth_controller: AuthController | None = None


def get_auth_controller() -> AuthController:
    global _auth_controller
    if _auth_controller is None:
        _auth_controller = AuthController()
    return _auth_controller
