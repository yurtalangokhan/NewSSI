from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query

from src.api.dependencies import require_permission
from src.controller.coarse_role_controller import get_role_controller

router = APIRouter(prefix="/coarse-roles", tags=["coarse-roles"])


@router.get("/")
async def list_coarse_roles(
    _user_id: Annotated[str, Depends(require_permission("permission:list"))],
    service_client: str | None = Query(None),
):
    ctrl = get_role_controller()
    return await ctrl.list_roles(service_client=service_client)


@router.post("/")
async def create_coarse_role(
    name: Annotated[str, Query()],
    service_client: Annotated[str, Query()],
    user_id: Annotated[str, Depends(require_permission("role:manage"))],
    description: str | None = Query(None),
    permissions: list[str] | None = None,
):
    ctrl = get_role_controller()
    return await ctrl.create_role(
        name=name,
        service_client=service_client,
        description=description,
        permissions=permissions,
        user_id=user_id,
    )


@router.get("/{role_name}")
async def get_coarse_role(
    role_name: str,
    _user_id: Annotated[str, Depends(require_permission("permission:list"))],
):
    ctrl = get_role_controller()
    return await ctrl.get_role(role_name)


@router.patch("/{role_name}")
async def update_coarse_role(
    role_name: str,
    user_id: Annotated[str, Depends(require_permission("role:manage"))],
    description: str | None = None,
    service_client: str | None = None,
):
    ctrl = get_role_controller()
    return await ctrl.update_role(
        name=role_name,
        description=description,
        service_client=service_client,
        user_id=user_id,
    )


@router.delete("/{role_name}")
async def delete_coarse_role(
    role_name: str,
    user_id: Annotated[str, Depends(require_permission("role:manage"))],
):
    ctrl = get_role_controller()
    return await ctrl.delete_role(role_name, user_id=user_id)


@router.get("/{role_name}/permissions")
async def get_coarse_role_permissions(
    role_name: str,
    _user_id: Annotated[str, Depends(require_permission("permission:list"))],
):
    ctrl = get_role_controller()
    return await ctrl.get_role_permissions(role_name)


@router.put("/{role_name}/permissions")
async def set_coarse_role_permissions(
    role_name: str,
    permissions: Annotated[list[str], Body(embed=True)],
    user_id: Annotated[str, Depends(require_permission("role:manage"))],
):
    ctrl = get_role_controller()
    return await ctrl.set_role_permissions(role_name, permissions, user_id=user_id)


@router.get("/aggregated/")
async def get_aggregated_permissions(
    names: Annotated[str, Query(description="Comma-separated role names")],
    _user_id: Annotated[str, Depends(require_permission("permission:list"))],
):
    ctrl = get_role_controller()
    role_names = [n.strip() for n in names.split(",") if n.strip()]
    return await ctrl.get_aggregated_permissions(role_names)


@router.get("/service-clients/list")
async def list_service_clients(
    _user_id: Annotated[str, Depends(require_permission("permission:list"))],
):
    ctrl = get_role_controller()
    return await ctrl.list_service_clients()
