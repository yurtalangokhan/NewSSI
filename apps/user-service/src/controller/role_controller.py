from typing import Any

from fastapi import HTTPException

from .base import BaseController


class RoleController(BaseController):
    def __init__(self):
        from src.service.role_service import get_role_service

        self.service = get_role_service()

    async def list_roles(self) -> dict[str, Any]:
        roles = await self.service.list_roles()
        return {"roles": roles}

    async def get_role(self, name: str) -> dict[str, Any]:
        role = await self.service.get_role(name)
        if not role:
            self._raise_not_found(f"Role '{name}' not found")
        return role

    async def create_role(
        self,
        name: str,
        description: str | None = None,
        permissions: list[str] | None = None,
    ) -> dict[str, Any]:
        try:
            return await self.service.create_role(
                name=name,
                description=description,
                permissions=permissions,
                is_builtin=False,
            )
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e

    async def update_role(
        self,
        name: str,
        description: str | None = None,
        permissions: list[str] | None = None,
    ) -> dict[str, Any]:
        try:
            role = await self.service.update_role(
                name=name,
                description=description,
                permissions=permissions,
            )
        except ValueError as e:
            self._raise_bad_request(str(e))
        if not role:
            self._raise_not_found(f"Role '{name}' not found")
        return role

    async def delete_role(self, name: str) -> dict[str, Any]:
        try:
            success = await self.service.delete_role(name)
        except ValueError as e:
            self._raise_bad_request(str(e))
        if not success:
            self._raise_not_found(f"Role '{name}' not found")
        return {"message": "Role deleted"}

    async def get_role_permissions(self, name: str) -> dict[str, Any]:
        try:
            result = await self.service.get_role_permissions(name)
        except Exception as e:
            self._raise_bad_request(str(e))
        if not result:
            self._raise_not_found(f"Role '{name}' not found")
        return result

    async def set_role_permissions(
        self, name: str, permissions: list[str]
    ) -> dict[str, Any]:
        try:
            result = await self.service.set_role_permissions(name, permissions)
        except ValueError as e:
            self._raise_bad_request(str(e))
        if not result:
            self._raise_not_found(f"Role '{name}' not found")
        return result

    async def sync_to_keycloak(self) -> dict[str, Any]:
        try:
            return await self.service.sync_to_keycloak()
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Keycloak sync failed: {e}"
            ) from e


_role_controller_instance: RoleController | None = None


def get_role_controller() -> RoleController:
    global _role_controller_instance
    if _role_controller_instance is None:
        _role_controller_instance = RoleController()
    return _role_controller_instance
