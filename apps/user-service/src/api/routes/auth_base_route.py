from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request, Response

from src.api.dependencies import require_auth, require_permission
from src.controller import get_auth_controller

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/type")
async def get_auth_type():
    return await get_auth_controller().get_auth_type()


@router.post("/login")
async def login(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
):
    return await get_auth_controller().login(request, response, username, password)


@router.post("/external/login")
async def external_login(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
):
    return await get_auth_controller().external_login(request, response, username, password)


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    post_logout_redirect_uri: str | None = Query(None),
):
    return await get_auth_controller().logout(request, response, post_logout_redirect_uri)


@router.post("/refresh")
async def refresh(
    request: Request,
    response: Response,
):
    return await get_auth_controller().refresh(request, response)


@router.get("/oidc/authorize")
async def oidc_authorize(
    redirect_uri: str | None = None,
    kc_idp_hint: str | None = None,
):
    return await get_auth_controller().oidc_authorize(redirect_uri, kc_idp_hint)


@router.get("/oidc/callback")
async def oidc_callback(
    request: Request,
    response: Response,
    code: str,
    redirect_uri: str | None = None,
):
    return await get_auth_controller().oidc_callback(request, response, code, redirect_uri)


@router.get("/me")
async def get_me(
    request: Request,
    user_id: Annotated[str, Depends(require_auth)],
):
    return await get_auth_controller().get_me(request, user_id)


@router.post("/sync-users")
async def sync_users(
    _admin_id: Annotated[str, Depends(require_permission("user:manage"))],
):
    """Sync users and roles from Keycloak into the local application DB."""
    return await get_auth_controller().sync_users_from_keycloak()
