"""Auth routes - provides endpoints for authentication and user management."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from api.dependencies import verify_api_key
from controller import AuthController, get_auth_controller

logger = logging.getLogger(__name__)

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
async def get_current_user(
    request: Request,
    user_id: Annotated[str | None, Depends(verify_api_key)],
) -> User:
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_data = await _get_controller().get_current_user(request=request, user_id=user_id)
    return User(**user_data)


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
async def logout(request: Request, response: Response):
    return await _get_controller().logout(request=request, response=response)


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


@router.get("/auth/oidc/authorize")
async def oidc_authorize(
    next_url: str | None = Query(default=None, alias="next"),
    redirect_uri: str | None = Query(default=None),
    redirect: bool = False,
):
    try:
        result = await _get_controller().get_oidc_authorize_url(
            next_url=next_url,
            redirect_uri_override=redirect_uri,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if redirect:
        return RedirectResponse(url=result["authorization_url"], status_code=307)
    return result


@router.get("/auth/oidc/callback")
async def oidc_callback(
    request: Request,
    response: Response,
):
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    redirect_uri = request.query_params.get("redirect_uri")

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    try:
        callback_result = await _get_controller().handle_oidc_callback(
            code=code,
            state=state,
            response=response,
            redirect_uri_override=redirect_uri,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("OIDC callback failed")
        raise HTTPException(status_code=401, detail=f"OIDC callback failed: {exc}") from exc

    redirect_url = callback_result.get("redirect_url", "/")
    redirect_response = RedirectResponse(url=redirect_url, status_code=307)

    # Move all cookies that were set on the injected Response object onto the redirect.
    for header_name, header_value in response.raw_headers:
        if header_name.lower() == b"set-cookie":
            redirect_response.raw_headers.append((header_name, header_value))

    return redirect_response


@router.get("/api/admin/mcp/servers")
async def get_mcp_servers():
    return await _get_controller().get_mcp_servers()