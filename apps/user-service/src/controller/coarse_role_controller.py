from typing import Any
import uuid

from localization import t

from src.core.exceptions import ConflictError

from .base import BaseController


class RoleController(BaseController):
    """Feature bundle use cases; every bundle is addressed by its Keycloak role ID."""

    def __init__(self):
        from src.service.coarse_role_service import get_role_service

        self.service = get_role_service()

    async def _audit(self, action: str, role_id: str, user_id: str | None, **details: Any):
        from src.service import get_audit_service

        await get_audit_service().log(
            action=action,
            resource=f"role:{role_id}",
            user_id=_safe_uuid(user_id),
            details=details,
        )

    def _found(self, role_id: str, result: dict[str, Any] | None) -> dict[str, Any]:
        if not result:
            self._raise_not_found("role.id_not_found", role_id=role_id)
        return result

    async def list_roles(self, service_client: str | None = None) -> dict[str, Any]:
        return {"roles": await self.service.list_roles(service_client=service_client)}

    async def get_role(self, role_id: str) -> dict[str, Any]:
        return self._found(role_id, await self.service.get_role(role_id))

    async def create_role(
        self,
        name: str,
        service_client: str,
        description: str | None = None,
        permissions: list[str] | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            role = await self.service.create_role(
                name=name,
                service_client=service_client,
                description=description,
                permissions=permissions,
            )
        except ConflictError:
            raise
        await self._audit(
            "role:create",
            role["id"],
            user_id,
            name=name,
            service_client=service_client,
            description=description,
        )
        return role

    async def update_role(
        self, role_id: str, description: str | None = None, user_id: str | None = None
    ) -> dict[str, Any]:
        role = self._found(role_id, await self.service.update_role(role_id, description))
        await self._audit("role:update", role_id, user_id, description=description)
        return role

    async def delete_role(self, role_id: str, user_id: str | None = None) -> dict[str, Any]:
        try:
            deleted = await self.service.delete_role(role_id)
        except ValueError as e:
            self._raise_bad_request(str(e))
        if not deleted:
            self._raise_not_found("role.id_not_found", role_id=role_id)
        await self._audit("role:delete", role_id, user_id)
        return {"message": t("role.deleted")}

    async def get_role_permissions(self, role_id: str) -> dict[str, Any]:
        return self._found(role_id, await self.service.get_role_permissions(role_id))

    async def set_role_permissions(
        self, role_id: str, permissions: list[str], user_id: str | None = None
    ) -> dict[str, Any]:
        result = await self.service.set_role_permissions(role_id, permissions)
        result = self._found(role_id, result)
        await self._audit("role:set_permissions", role_id, user_id, permissions_count=len(permissions))
        return result

    async def list_service_clients(self) -> dict[str, Any]:
        return {"service_clients": await self.service.list_service_clients()}

    async def get_aggregated_permissions(self, role_ids: list[str]) -> dict[str, Any]:
        return {"permissions": await self.service.get_aggregated_permissions(role_ids)}


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
