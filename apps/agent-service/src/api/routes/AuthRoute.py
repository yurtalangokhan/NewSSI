"""Authentication-adjacent routes for token-backed agent-service requests."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from api.dependencies import AuthenticatedUser, require_user
from controller import AuthController, get_auth_controller
from models.auth import Settings, User

router = APIRouter(tags=["auth"])


def _get_controller() -> AuthController:
    return get_auth_controller()


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
