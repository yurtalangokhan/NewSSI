from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.api.dependencies import require_permission
from src.controller.permission_controller import get_permission_controller

router = APIRouter(prefix="/permissions", tags=["permissions"])


@router.get("/")
async def list_permissions(
    _user_id: Annotated[str, Depends(require_permission("permission:list"))],
    service: str | None = Query(None),
):
    ctrl = get_permission_controller()
    return await ctrl.list_permissions(service=service)


@router.get("/entities")
async def list_entities(
    _user_id: Annotated[str, Depends(require_permission("permission:list"))],
):
    ctrl = get_permission_controller()
    return await ctrl.list_entities()


@router.get("/services")
async def list_services(
    _user_id: Annotated[str, Depends(require_permission("permission:list"))],
):
    ctrl = get_permission_controller()
    return await ctrl.list_services()


@router.post("/sync")
async def sync_permissions(
    _user_id: Annotated[str, Depends(require_permission("permission:manage"))],
):
    ctrl = get_permission_controller()
    return await ctrl.sync_permissions()


@router.get("/{permission_name}")
async def get_permission(
    permission_name: str,
    _user_id: Annotated[str, Depends(require_permission("permission:read"))],
):
    ctrl = get_permission_controller()
    return await ctrl.get_permission(permission_name)
