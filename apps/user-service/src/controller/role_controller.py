from typing import Any
import uuid

from localization import t

from src.core.exceptions import ConflictError

from .base import BaseController


class CompositeRoleController(BaseController):
    """Platform role use cases; every role is addressed by its Keycloak role ID."""

    def __init__(self):
        from src.service.role_service import get_composite_role_service

        self.service = get_composite_role_service()

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

    async def list_roles(self) -> dict[str, Any]:
        return {"roles": await self.service.list_roles()}

    async def get_role(self, role_id: str) -> dict[str, Any]:
        return self._found(role_id, await self.service.get_role(role_id))

    async def create_role(
        self,
        name: str,
        description: str | None = None,
        permissions: list[str] | None = None,
        role_ids: list[str] | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            role = await self.service.create_role(
                name=name, description=description, permissions=permissions, role_ids=role_ids
            )
        except ConflictError:
            raise
        await self._audit(
            "role:create",
            role["id"],
            user_id,
            name=name,
            description=description,
            permissions=permissions,
            role_ids=role_ids,
        )
        return role

    async def update_role(
        self,
        role_id: str,
        description: str | None = None,
        permissions: list[str] | None = None,
        role_ids: list[str] | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        role = await self.service.update_role(
            role_id, description=description, permissions=permissions, role_ids=role_ids
        )
        role = self._found(role_id, role)
        await self._audit(
            "role:update",
            role_id,
            user_id,
            description=description,
            permissions=permissions,
            role_ids=role_ids,
        )
        return role

    async def delete_role(self, role_id: str, user_id: str | None = None) -> dict[str, Any]:
        deleted = await self.service.delete_role(role_id)
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
        await self._audit("role:set_permissions", role_id, user_id, permissions=permissions)
        return result

    async def get_role_bundles(self, role_id: str) -> dict[str, Any]:
        return self._found(role_id, await self.service.get_role_bundles(role_id))

    async def set_role_bundles(self, role_id: str, role_ids: list[str], user_id: str | None = None) -> dict[str, Any]:
        result = await self.service.set_role_bundles(role_id, role_ids)
        result = self._found(role_id, result)
        await self._audit("role:set_role_ids", role_id, user_id, role_ids=role_ids)
        return result


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
