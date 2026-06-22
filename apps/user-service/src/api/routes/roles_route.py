from fastapi import APIRouter, Body, Depends

from src.api.dependencies import require_auth, require_permission
from src.controller.role_controller import get_role_controller

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get("/")
async def list_roles(user_id: str = Depends(require_auth)):
    ctrl = get_role_controller()
    return await ctrl.list_roles()


@router.post("/")
async def create_role(
    name: str,
    description: str | None = None,
    permissions: list[str] | None = None,
    user_id: str = Depends(require_permission("role:manage")),
):
    ctrl = get_role_controller()
    return await ctrl.create_role(
        name=name,
        description=description,
        permissions=permissions,
        user_id=user_id,
    )


@router.get("/{role_name}")
async def get_role(role_name: str, user_id: str = Depends(require_auth)):
    ctrl = get_role_controller()
    return await ctrl.get_role(role_name)


@router.patch("/{role_name}")
async def update_role(
    role_name: str,
    description: str | None = None,
    permissions: list[str] | None = None,
    user_id: str = Depends(require_permission("role:manage")),
):
    ctrl = get_role_controller()
    return await ctrl.update_role(
        name=role_name,
        description=description,
        permissions=permissions,
        user_id=user_id,
    )


@router.delete("/{role_name}")
async def delete_role(role_name: str, user_id: str = Depends(require_permission("role:manage"))):
    ctrl = get_role_controller()
    return await ctrl.delete_role(role_name, user_id=user_id)


@router.get("/{role_name}/permissions")
async def get_role_permissions(
    role_name: str,
    user_id: str = Depends(require_auth),
):
    ctrl = get_role_controller()
    return await ctrl.get_role_permissions(role_name)


@router.put("/{role_name}/permissions")
async def set_role_permissions(
    role_name: str,
    permissions: list[str] = Body(..., embed=True),
    user_id: str = Depends(require_permission("role:manage")),
):
    ctrl = get_role_controller()
    return await ctrl.set_role_permissions(role_name, permissions, user_id=user_id)


@router.post("/sync-keycloak")
async def sync_roles_to_keycloak(
    user_id: str = Depends(require_permission("role:manage")),
):
    ctrl = get_role_controller()
    return await ctrl.sync_to_keycloak(user_id=user_id)
