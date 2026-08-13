import uuid
from typing import Any

from fastapi import HTTPException
from i18n import t

from .base import BaseController


class RoleController(BaseController):
    def __init__(self):
        from src.service.coarse_role_service import get_role_service

        self.service = get_role_service()

    async def list_roles(self, service_client: str | None = None) -> dict[str, Any]:
        roles = await self.service.list_roles(service_client=service_client)
        return {"roles": roles}

    async def get_role(self, name: str) -> dict[str, Any]:
        role = await self.service.get_role(name)
        if not role:
            self._raise_not_found("role.not_found", name=name)
        return role

    async def create_role(
        self,
        name: str,
        service_client: str,
        description: str | None = None,
        permissions: list[str] | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        from src.service import get_audit_service

        try:
            result = await self.service.create_role(
                name=name,
                service_client=service_client,
                description=description,
                permissions=permissions,
            )
            audit = get_audit_service()
            await audit.log(
                action="role:create",
                resource=f"role:{name}",
                user_id=_safe_uuid(user_id),
                details={
                    "name": name,
                    "service_client": service_client,
                    "description": description,
                },
            )
            return result
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e

    async def update_role(
        self,
        name: str,
        description: str | None = None,
        service_client: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        from src.service import get_audit_service

        role = await self.service.update_role(
            name=name,
            description=description,
            service_client=service_client,
        )
        if not role:
            self._raise_not_found("role.not_found", name=name)
        audit = get_audit_service()
        await audit.log(
            action="role:update",
            resource=f"role:{name}",
            user_id=_safe_uuid(user_id),
            details={"description": description, "service_client": service_client},
        )
        return role

    async def delete_role(self, name: str, user_id: str | None = None) -> dict[str, Any]:
        from src.service import get_audit_service

        success = await self.service.delete_role(name)
        if not success:
            self._raise_not_found("role.not_found", name=name)
        audit = get_audit_service()
        await audit.log(
            action="role:delete",
            resource=f"role:{name}",
            user_id=_safe_uuid(user_id),
            details={"name": name},
        )
        return {"message": t("role.deleted")}

    async def get_role_permissions(self, name: str) -> dict[str, Any]:
        result = await self.service.get_role_permissions(name)
        if not result:
            self._raise_not_found("role.not_found", name=name)
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
            self._raise_not_found("role.not_found", name=name)
        audit = get_audit_service()
        await audit.log(
            action="role:set_permissions",
            resource=f"role:{name}",
            user_id=_safe_uuid(user_id),
            details={"name": name, "permissions_count": len(permissions)},
        )
        return result

    async def list_service_clients(self) -> dict[str, Any]:
        clients = await self.service.list_service_clients()
        return {"service_clients": clients}

    async def get_aggregated_permissions(self, names: list[str]) -> dict[str, Any]:
        perms = await self.service.get_aggregated_permissions(names)
        return {"permissions": perms}


def _safe_uuid(val: str | None) -> uuid.UUID | None:
    if not val:
        return None
    try:
        return uuid.UUID(val)
    except (ValueError, AttributeError):
        return None


_role_controller_instance: RoleController | None = None


def get_role_controller() -> RoleController:
    global _role_controller_instance
    if _role_controller_instance is None:
        _role_controller_instance = RoleController()
    return _role_controller_instance
