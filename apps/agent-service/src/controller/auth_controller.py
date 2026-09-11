"""Auth-adjacent controller for token-backed agent-service routes."""

from typing import Any

from fastapi import Request

from api.dependencies import extract_auth_token_from_request
from controller.base import BaseController
from service.AuthService import AuthenticatedUser, get_auth_service


class AuthController(BaseController):
    """Controller for user context endpoints that consume existing tokens."""

    def __init__(self):
        self._auth_service = get_auth_service()

    async def get_current_user(self, request: Request, user: AuthenticatedUser) -> dict[str, Any]:
        token = extract_auth_token_from_request(request)
        return await self._auth_service.get_current_user(token=token, user=user)

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


_auth_controller: AuthController | None = None


def get_auth_controller() -> AuthController:
    global _auth_controller
    if _auth_controller is None:
        _auth_controller = AuthController()
    return _auth_controller
