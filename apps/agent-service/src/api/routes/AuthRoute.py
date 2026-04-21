"""Auth routes - provides endpoints for authentication and user management."""

import logging

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from controller import AuthMetadataController, get_auth_metadata_controller

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])


def _get_controller() -> AuthMetadataController:
    return get_auth_metadata_controller()


class User(BaseModel):
    id: str = "dev-user-1"
    email: str = "dev@local.dev"
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


class AuthTypeMetadata(BaseModel):
    authType: str = "basic"
    autoRedirect: bool = False
    requiresVerification: bool = False
    anonymousUserEnabled: bool = False
    passwordMinLength: int = 8
    hasUsers: bool = True
    oauthEnabled: bool = False


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


class CombinedSettings(BaseModel):
    settings: Settings = Settings()
    enterpriseSettings: str | None = None
    customAnalyticsScript: str | None = None
    webVersion: str = "dev"
    webDomain: str = "http://localhost:3000"
    product: str = "Agentic AI"


@router.get("/auth/type")
async def get_auth_type() -> AuthTypeMetadata:
    return AuthTypeMetadata(**(await _get_controller().get_auth_type()))


@router.get("/me")
async def get_current_user() -> User:
    return User(**(await _get_controller().get_current_user()))


@router.post("/auth/login")
async def login(request: Request, response: Response):
    try:
        content_type = request.headers.get("content-type", "")

        if "application/x-www-form-urlencoded" in content_type:
            body = await request.form()
            username = body.get("username", "")
            password = body.get("password", "")
        else:
            body = await request.json()
            username = body.get("username", "")
            password = body.get("password", "")

        return await _get_controller().login(username=username, password=password, response=response)
    except Exception as e:
        logger.error(f"Login error: {e}")
        response.status_code = 500
        return {"success": False, "error": str(e)}


@router.post("/auth/logout")
async def logout(response: Response):
    return await _get_controller().logout(response=response)


@router.get("/settings")
async def get_settings() -> Settings:
    return Settings(**(await _get_controller().get_settings()))


@router.get("/enterprise-settings")
async def get_enterprise_settings() -> dict:
    return await _get_controller().get_enterprise_settings()


@router.get("/health")
async def health_check():
    return await _get_controller().health_check()


@router.post("/api/auth/refresh")
async def refresh_auth():
    return await _get_controller().refresh_auth()


@router.get("/api/admin/mcp/servers")
async def get_mcp_servers():
    return await _get_controller().get_mcp_servers()