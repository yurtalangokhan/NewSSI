from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response
from pydantic import BaseModel

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
async def logout(request: Request, response: Response):
    return await get_auth_controller().logout(request, response)


@router.post("/refresh")
async def refresh(request: Request, response: Response):
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
async def get_me(user_id: Annotated[str, Depends(require_auth)]):
    from src.service import get_user_service

    user = await get_user_service().get_current_user(user_id)
    if not user:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="User not found")
    return user


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    first_name: str | None = None
    last_name: str | None = None


@router.post("/register")
async def register(
    request: Request,
    response: Response,
    body: RegisterRequest,
):
    return await get_auth_controller().register(
        request,
        response,
        username=body.username,
        email=body.email,
        password=body.password,
        first_name=body.first_name,
        last_name=body.last_name,
    )


@router.post("/sync-users")
async def sync_users(admin_id: Annotated[str, Depends(require_admin)]):
    """Sync all users and roles from Keycloak to user-service DB.

    Admin-only endpoint. Performs one-time or periodic sync:
    - Creates/updates users from Keycloak
    - Deletes orphaned users (in DB but not in Keycloak)
    - Syncs realm roles
    """
    return await get_auth_controller().sync_users_from_keycloak()
