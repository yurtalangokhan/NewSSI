"""Controller for auth metadata and session-oriented auth endpoints."""

import logging
import os
from datetime import UTC, datetime
from typing import Any

from fastapi import Response

from controller.base import BaseController

logger = logging.getLogger(__name__)


class AuthMetadataController(BaseController):
    """Controller for auth metadata, user info, and auth session helpers."""

    def __init__(self, user_id: str = "dev-user-1"):
        self._user_id = user_id

    async def get_auth_type(self) -> dict[str, Any]:
        return {
            "authType": "basic",
            "autoRedirect": False,
            "requiresVerification": False,
            "anonymousUserEnabled": False,
            "passwordMinLength": 8,
            "hasUsers": True,
            "oauthEnabled": False,
        }

    async def get_current_user(self) -> dict[str, Any]:
        return {
            "id": self._user_id,
            "email": "dev@local.dev",
            "is_active": True,
            "is_superuser": True,
            "is_verified": True,
            "role": "admin",
            "preferences": {
                "chosen_assistants": None,
                "visible_assistants": [],
                "hidden_assistants": [],
                "default_model": None,
                "recent_assistants": [],
                "auto_scroll": True,
                "shortcut_enabled": True,
                "temperature_override_enabled": False,
                "theme_preference": None,
                "chat_background": None,
                "default_app_mode": "AUTO",
            },
            "team_name": None,
            "is_anonymous_user": False,
            "password_configured": True,
        }

    async def login(self, username: str, password: str, response: Response) -> dict[str, Any]:
        if username and password:
            response.set_cookie("session", "dev-session", httponly=True, samesite="lax")
            return {
                "success": True,
                "user_id": self._user_id,
                "email": f"{username}@example.com",
            }

        response.status_code = 400
        return {"success": False, "error": "Missing credentials"}

    async def logout(self, response: Response) -> dict[str, Any]:
        response.delete_cookie("session")
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

    async def get_mcp_servers(self) -> dict[str, Any]:
        mcp_servers = []
        tools_service_url = os.getenv("TOOLS_SERVICE_URL", "http://localhost:8003")

        if tools_service_url:
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


_auth_metadata_controller: AuthMetadataController | None = None


def get_auth_metadata_controller() -> AuthMetadataController:
    """Get singleton AuthMetadataController."""
    global _auth_metadata_controller
    if _auth_metadata_controller is None:
        _auth_metadata_controller = AuthMetadataController()
    return _auth_metadata_controller
