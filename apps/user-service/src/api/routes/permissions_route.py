from fastapi import APIRouter, Depends, Query

from src.api.dependencies import require_auth
from src.controller.permission_controller import get_permission_controller

router = APIRouter(prefix="/permissions", tags=["permissions"])


@router.get("/")
async def list_permissions(
    service: str | None = Query(None),
    _user_id: str = Depends(require_auth),
):
    ctrl = get_permission_controller()
    return await ctrl.list_permissions(service=service)


@router.get("/entities")
async def list_entities(
    _user_id: str = Depends(require_auth),
):
    ctrl = get_permission_controller()
    return await ctrl.list_entities()


@router.get("/services")
async def list_services(
    _user_id: str = Depends(require_auth),
):
    ctrl = get_permission_controller()
    return await ctrl.list_services()


@router.get("/{permission_name}")
async def get_permission(
    permission_name: str,
    _user_id: str = Depends(require_auth),
):
    ctrl = get_permission_controller()
    return await ctrl.get_permission(permission_name)
