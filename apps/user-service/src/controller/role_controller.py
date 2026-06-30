import uuid
from typing import Any

from fastapi import HTTPException

from .base import BaseController


class CompositeRoleController(BaseController):
    def __init__(self):
        from src.service.role_service import get_composite_role_service

        self.service = get_composite_role_service()

    async def list_roles(self) -> dict[str, Any]:
        roles = await self.service.list_roles()
        return {"composite_roles": roles, "roles": roles}

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
        role_ids: list[str] | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        from src.service import get_audit_service

        try:
            result = await self.service.create_role(
                name=name,
                description=description,
                permissions=permissions,
                role_ids=role_ids,
                is_builtin=False,
            )
            audit = get_audit_service()
            await audit.log(
                action="role:create",
                resource=f"role:{name}",
                user_id=_safe_uuid(user_id),
                details={"name": name, "description": description, "permissions": permissions},
            )
            return result
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e

    async def update_role(
        self,
        name: str,
        description: str | None = None,
        permissions: list[str] | None = None,
        role_ids: list[str] | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        from src.service import get_audit_service

        try:
            role = await self.service.update_role(
                name=name,
                description=description,
                permissions=permissions,
                role_ids=role_ids,
            )
        except ValueError as e:
            self._raise_bad_request(str(e))
        if not role:
            self._raise_not_found(f"Role '{name}' not found")
        audit = get_audit_service()
        await audit.log(
            action="role:update",
            resource=f"role:{name}",
            user_id=_safe_uuid(user_id),
            details={"description": description, "permissions": permissions, "role_ids": role_ids},
        )
        return role

    async def delete_role(self, name: str, user_id: str | None = None) -> dict[str, Any]:
        from src.service import get_audit_service

        try:
            success = await self.service.delete_role(name)
        except ValueError as e:
            self._raise_bad_request(str(e))
        if not success:
            self._raise_not_found(f"Role '{name}' not found")
        audit = get_audit_service()
        await audit.log(
            action="role:delete",
            resource=f"role:{name}",
            user_id=_safe_uuid(user_id),
            details={"name": name},
        )
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
        self, name: str, permissions: list[str], user_id: str | None = None
    ) -> dict[str, Any]:
        from src.service import get_audit_service

        try:
            result = await self.service.set_role_permissions(name, permissions)
        except ValueError as e:
            self._raise_bad_request(str(e))
        if not result:
            self._raise_not_found(f"Role '{name}' not found")
        audit = get_audit_service()
        await audit.log(
            action="role:set_permissions",
            resource=f"role:{name}",
            user_id=_safe_uuid(user_id),
            details={"name": name, "permissions": permissions},
        )
        return result

    async def get_role_role_ids(self, name: str) -> dict[str, Any]:
        result = await self.service.get_role_role_ids(name)
        if not result:
            self._raise_not_found(f"Role '{name}' not found")
        return result

    async def set_role_role_ids(
        self, name: str, role_ids: list[str], user_id: str | None = None
    ) -> dict[str, Any]:
        from src.service import get_audit_service

        try:
            result = await self.service.set_role_role_ids(name, role_ids)
        except ValueError as e:
            self._raise_bad_request(str(e))
        if not result:
            self._raise_not_found(f"Role '{name}' not found")
        audit = get_audit_service()
        await audit.log(
            action="role:set_role_ids",
            resource=f"role:{name}",
            user_id=_safe_uuid(user_id),
            details={"name": name, "role_ids": role_ids},
        )
        return result

    async def sync_to_keycloak(self, user_id: str | None = None) -> dict[str, Any]:
        from src.service import get_audit_service

        try:
            result = await self.service.sync_to_keycloak()
            audit = get_audit_service()
            await audit.log(
                action="role:sync_keycloak",
                resource="keycloak:roles",
                user_id=_safe_uuid(user_id),
                details={},
            )
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Keycloak sync failed: {e}") from e


def _safe_uuid(val: str | None) -> uuid.UUID | None:
    if not val:
        return None
    try:
        return uuid.UUID(val)
    except (ValueError, AttributeError):
        return None


_composite_role_controller_instance: CompositeRoleController | None = None


def get_composite_role_controller() -> CompositeRoleController:
    global _composite_role_controller_instance
    if _composite_role_controller_instance is None:
        _composite_role_controller_instance = CompositeRoleController()
    return _composite_role_controller_instance
