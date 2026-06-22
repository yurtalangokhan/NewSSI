"""Authentication-adjacent routes for token-backed agent-service requests."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from api.dependencies import AuthenticatedUser, require_user
from controller import AuthController, get_auth_controller

router = APIRouter(tags=["auth"])


def _get_controller() -> AuthController:
    return get_auth_controller()


class User(BaseModel):
    id: str = "dev-user-1"
    email: str = "dev@local.dev"
    username: str | None = None
    is_active: bool = True
    is_superuser: bool = True
    is_verified: bool = True
    role: str = "admin"
    preferences: dict = {
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
    }
    team_name: str | None = None
    is_anonymous_user: bool = False
    password_configured: bool = True
    first_name: str | None = None
    full_name: str | None = None
    personalization: dict | None = None


class Settings(BaseModel):
    auto_scroll: bool = True
    application_status: str = "active"
    gpu_enabled: bool = False
    maximum_chat_retention_days: str | None = None
    notifications: list = []
    needs_reindexing: bool = False
    anonymous_user_enabled: bool = False
    invite_only_enabled: bool = False
    deep_research_enabled: bool = True
    temperature_override_enabled: bool = True
    query_history_type: str = "normal"


@router.get("/me")
async def get_current_user(
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> User:
    user_data = await _get_controller().get_current_user(request=request, user=user)
    return User(**user_data)


@router.get("/settings")
async def get_settings(
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> Settings:
    return Settings(**(await _get_controller().get_settings()))


@router.get("/enterprise-settings")
async def get_enterprise_settings(
    user: Annotated[AuthenticatedUser, Depends(require_user)],
) -> dict:
    return await _get_controller().get_enterprise_settings()


@router.get("/health")
async def health_check():
    return await _get_controller().health_check()


@router.get("/api/admin/mcp/servers")
async def get_mcp_servers(
    user: Annotated[AuthenticatedUser, Depends(require_user)],
):
    return await _get_controller().get_mcp_servers()
