from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response

from src.api.dependencies import require_admin, require_auth
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


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    user_id: Annotated[str, Depends(require_auth)],
):
    return await get_auth_controller().logout(request, response)


@router.post("/refresh")
async def refresh(
    request: Request,
    response: Response,
    user_id: Annotated[str, Depends(require_auth)],
):
    return await get_auth_controller().refresh(request, response)


@router.get("/oidc/authorize")
async def oidc_authorize(redirect_uri: str | None = None):
    return await get_auth_controller().oidc_authorize(redirect_uri)


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
async def sync_users(admin_id: Annotated[str, Depends(require_admin)]):
    """Sync users and roles from Keycloak into the local application DB."""
    return await get_auth_controller().sync_users_from_keycloak()
