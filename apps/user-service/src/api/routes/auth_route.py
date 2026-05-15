from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response

from src.api.dependencies import require_auth
from src.controller import get_auth_controller

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/type")
async def get_auth_type():
    return await get_auth_controller().get_auth_type()


@router.post("/login")
async def login(
    request: Request,
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
):
    return await get_auth_controller().login(request, response, email, password)


@router.post("/logout")
async def logout(request: Request, response: Response):
    return await get_auth_controller().logout(request, response)


@router.post("/refresh")
async def refresh(
    response: Response,
    refresh_token: Annotated[str | None, Form(...)] = None,
):
    return await get_auth_controller().refresh(refresh_token)


@router.get("/oidc/authorize")
async def oidc_authorize(redirect_uri: str | None = None):
    return await get_auth_controller().oidc_authorize(redirect_uri)


@router.get("/oidc/callback")
async def oidc_callback(code: str, redirect_uri: str | None = None):
    return await get_auth_controller().oidc_callback(code, redirect_uri)


@router.get("/me")
async def get_me(user_id: Annotated[str, Depends(require_auth)]):
    from src.service import get_user_service
    user = await get_user_service().get_current_user(user_id)
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="User not found")
    return user
