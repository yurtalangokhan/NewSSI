from fastapi import APIRouter, Depends

from src.api.dependencies import require_admin, require_auth
from src.repository import RoleRepository

router = APIRouter(prefix="/roles", tags=["roles"])

SUPPORTED_ROLES = {"admin", "enduser"}


@router.get("/")
async def list_roles(user_id: str = Depends(require_auth)):
    repo = RoleRepository()
    roles = await repo.get_all()
    return {
        "roles": [
            {
                "name": r.name,
                "description": r.description,
                "permissions": r.permissions,
                "is_builtin": r.is_builtin,
            }
            for r in roles
        ]
    }


@router.post("/")
async def create_role(
    name: str,
    description: str | None = None,
    permissions: list[str] | None = None,
    user_id: str = Depends(require_admin),
):
    repo = RoleRepository()
    if name not in SUPPORTED_ROLES:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="Only admin and enduser roles are supported")
    if await repo.exists(name):
        from fastapi import HTTPException

        raise HTTPException(status_code=409, detail="Role already exists")
    role = await repo.create(
        name=name, description=description, permissions=permissions, is_builtin=False
    )
    return {
        "name": role.name,
        "description": role.description,
        "permissions": role.permissions,
        "is_builtin": role.is_builtin,
    }


@router.get("/{role_name}")
async def get_role(role_name: str, user_id: str = Depends(require_auth)):
    repo = RoleRepository()
    role = await repo.get_by_name(role_name)
    if not role:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Role not found")
    return {
        "name": role.name,
        "description": role.description,
        "permissions": role.permissions,
        "is_builtin": role.is_builtin,
    }


@router.patch("/{role_name}")
async def update_role(
    role_name: str,
    description: str | None = None,
    permissions: list[str] | None = None,
    user_id: str = Depends(require_admin),
):
    repo = RoleRepository()
    if role_name not in SUPPORTED_ROLES:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="Only admin and enduser roles are supported")
    role = await repo.update(role_name, description=description, permissions=permissions)
    if not role:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Role not found")
    return {
        "name": role.name,
        "description": role.description,
        "permissions": role.permissions,
        "is_builtin": role.is_builtin,
    }


@router.delete("/{role_name}")
async def delete_role(role_name: str, user_id: str = Depends(require_admin)):
    if role_name in SUPPORTED_ROLES:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="Cannot delete supported role")
    repo = RoleRepository()
    role = await repo.get_by_name(role_name)
    if role and role.is_builtin:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="Cannot delete builtin role")
    success = await repo.delete(role_name)
    if not success:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Role not found")
    return {"message": "Role deleted"}
