"""Auth controller — thin orchestrator delegating to AuthService."""

import logging
import os
from typing import Any

from fastapi import Request, Response

from controller.base import BaseController
from service.AuthService import get_auth_service

logger = logging.getLogger(__name__)


class AuthController(BaseController):
    """Controller for authentication endpoints.

    Thin orchestrator: delegates all business logic to AuthService.
    Manages HTTP-specific concerns (cookie setting).
    """

    def __init__(self):
        self._auth_service = get_auth_service()

    async def get_auth_type(self) -> dict[str, Any]:
        return await self._auth_service.get_auth_type()

    async def get_current_user(self, request: Request, user_id: str) -> dict[str, Any]:
        return await self._auth_service.get_current_user(request=request, user_id=user_id)

    async def login(self, username: str, password: str, response: Response) -> dict[str, Any]:
        result = await self._auth_service.basic_login(username=username, password=password)

        if result.get("success"):
            response.set_cookie("session", "dev-session", httponly=True, samesite="lax")

        if not result.get("success"):
            response.status_code = 400

        return result

    async def logout(self, request: Request, response: Response) -> dict[str, Any]:
        refresh_token = request.cookies.get("refresh_token")
        id_token_hint = request.cookies.get("id_token")

        await self._auth_service.logout(
            refresh_token=refresh_token,
            id_token_hint=id_token_hint,
        )

        cookies_to_delete = ["session", "fastapiusersauth", "id_token", "refresh_token", "access_token"]
        for cookie_name in cookies_to_delete:
            response.delete_cookie(cookie_name, path="/", samesite="lax")

        return {"success": True}

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

    async def refresh_auth(self) -> dict[str, Any]:
        return {"success": True}

    async def get_oidc_authorize_url(
        self,
        next_url: str | None = None,
        redirect_uri_override: str | None = None,
    ) -> dict[str, str]:
        return await self._auth_service.get_oidc_authorize_url(
            next_url=next_url,
            redirect_uri_override=redirect_uri_override,
        )

    async def handle_oidc_callback(
        self,
        code: str,
        state: str | None,
        response: Response,
        redirect_uri_override: str | None = None,
    ) -> dict[str, Any]:
        result = await self._auth_service.handle_oidc_callback(
            code=code,
            state=state,
            redirect_uri_override=redirect_uri_override,
        )

        access_token = result.get("access_token")
        id_token = result.get("id_token")
        refresh_token = result.get("refresh_token")
        expires_in = result.get("expires_in", 3600)

        response.set_cookie(
            "fastapiusersauth", access_token, httponly=True, samesite="lax",
            max_age=expires_in, path="/",
        )
        response.set_cookie(
            "session", access_token, httponly=True, samesite="lax",
            max_age=expires_in, path="/",
        )
        if refresh_token:
            response.set_cookie(
                "refresh_token", refresh_token, httponly=True, samesite="lax",
                max_age=7 * 24 * 3600, path="/",
            )
        if id_token:
            response.set_cookie(
                "id_token", id_token, httponly=True, samesite="lax",
                max_age=expires_in, path="/",
            )

        return result

    async def get_mcp_servers(self) -> dict[str, Any]:
        mcp_servers = []
        tools_service_url = (
            os.getenv("TOOLS_SERVICE_URL")
            or os.getenv("MCP_SERVER_URL")
            or "http://localhost:8003"
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
