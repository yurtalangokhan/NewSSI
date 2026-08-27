"""HTTP error translation for resource permission operations."""

import uuid
from typing import Any

from src.core.exceptions import ForbiddenError, NotFoundError
from src.service import get_permission_audit_service, get_resource_permission_service

from .base import BaseController


class ResourcePermissionController(BaseController):
    """Coordinate resource permission requests and translate domain errors for HTTP."""

    def __init__(self) -> None:
        self.service = get_resource_permission_service()
        self.audit_service = get_permission_audit_service()

    async def get_scoped_direct_permissions(
        self,
        actor_id: uuid.UUID,
        organization_id: uuid.UUID,
        target_type: str,
        target_id: uuid.UUID,
        resource_type: str,
    ) -> dict[str, Any]:
        try:
            permissions = await self.service.get_scoped_direct_permissions(
                actor_id=actor_id,
                organization_id=organization_id,
                target_type=target_type,
                target_id=target_id,
                resource_type=resource_type,
            )
            return {"permissions": permissions, "count": len(permissions)}
        except ForbiddenError as error:
            self._raise_forbidden(str(error))
        except NotFoundError as error:
            self._raise_not_found(str(error))
        except ValueError as error:
            self._raise_bad_request(str(error))

    async def sync_scoped_direct_permissions(
        self,
        actor_id: uuid.UUID,
        organization_id: uuid.UUID,
        target_type: str,
        target_id: uuid.UUID,
        resource_type: str,
        desired_permissions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            permissions = await self.service.sync_scoped_direct_permissions(
                actor_id=actor_id,
                organization_id=organization_id,
                target_type=target_type,
                target_id=target_id,
                resource_type=resource_type,
                desired_permissions=desired_permissions,
            )
            return {"permissions": permissions, "count": len(permissions)}
        except ForbiddenError as error:
            self._raise_forbidden(str(error))
        except NotFoundError as error:
            self._raise_not_found(str(error))
        except ValueError as error:
            self._raise_bad_request(str(error))

    async def check_permission(
        self,
        user_id: uuid.UUID,
        resource_type: str,
        resource_id: str,
        required_permission: str = "read",
    ) -> dict[str, Any]:
        return await self.service.check_resource_access(
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            required_permission=required_permission,
        )

    async def grant_organization_permission(
        self,
        org_id: uuid.UUID,
        resource_type: str,
        resource_id: str,
        resource_name: str | None,
        permission_level: str,
        granted_by: uuid.UUID,
    ) -> dict[str, Any]:
        try:
            return await self.service.grant_permission(
                resource_type=resource_type,
                resource_id=resource_id,
                resource_name=resource_name,
                organization_id=org_id,
                permission_level=permission_level,
                granted_by=granted_by,
            )
        except ValueError as e:
            self._raise_bad_request(str(e))

    async def get_organization_permissions(
        self, organization_id: uuid.UUID, resource_type: str | None = None
    ) -> dict[str, Any]:
        perms = await self.service.get_organization_permissions(organization_id, resource_type)
        return {"permissions": perms, "count": len(perms)}

    async def grant_user_permission(
        self,
        target_user_id: uuid.UUID,
        resource_type: str,
        resource_id: str,
        resource_name: str | None,
        permission_level: str,
        granted_by: uuid.UUID,
    ) -> dict[str, Any]:
        try:
            return await self.service.grant_permission(
                resource_type=resource_type,
                resource_id=resource_id,
                resource_name=resource_name,
                user_id=target_user_id,
                permission_level=permission_level,
                granted_by=granted_by,
            )
        except ValueError as e:
            self._raise_bad_request(str(e))

    async def get_user_permissions_listing(
        self, user_id: uuid.UUID, resource_type: str | None = None
    ) -> dict[str, Any]:
        perms = await self.service.get_user_permissions_listing(user_id, resource_type)
        return {"permissions": perms, "count": len(perms)}

    async def get_user_accessible_resources(
        self, user_id: uuid.UUID, resource_type: str | None = None
    ) -> dict[str, Any]:
        resources = await self.service.get_user_accessible_resources(user_id, resource_type)
        return {"resources": resources, "count": len(resources)}

    async def get_resource_permissions(
        self, resource_type: str, resource_id: str
    ) -> dict[str, Any]:
        perms = await self.service.get_resource_permissions(resource_type, resource_id)
        return {"permissions": perms, "count": len(perms)}

    async def update_permission(
        self,
        permission_id: uuid.UUID,
        permission_level: str,
        updated_by: uuid.UUID,
    ) -> dict[str, Any]:
        try:
            return await self.service.update_permission(permission_id, permission_level, updated_by)
        except ValueError as e:
            self._raise_bad_request(str(e))

    async def revoke_permission(
        self, permission_id: uuid.UUID, revoked_by: uuid.UUID
    ) -> dict[str, Any]:
        try:
            deleted = await self.service.revoke_permission(permission_id, revoked_by)
            if not deleted:
                self._raise_not_found("permission.not_found")
            return {"success": True}
        except ValueError as e:
            self._raise_bad_request(str(e))

    async def bulk_grant_permissions(
        self,
        resource_type: str,
        resource_id: str,
        resource_name: str,
        grants: list[dict[str, Any]],
        granted_by: uuid.UUID,
    ) -> dict[str, Any]:
        return await self.service.bulk_grant_permissions(
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            grants=grants,
            granted_by=granted_by,
        )

    async def get_resource_audit_logs(
        self, resource_type: str, resource_id: str, skip: int = 0, limit: int = 50
    ) -> dict[str, Any]:
        logs, total = await self.audit_service.get_resource_audit_logs(
            resource_type, resource_id, skip, limit
        )
        return {"logs": logs, "total": total, "skip": skip, "limit": limit}

    async def get_organization_audit_logs(
        self, org_id: uuid.UUID, skip: int = 0, limit: int = 50
    ) -> dict[str, Any]:
        logs, total = await self.audit_service.get_target_audit_logs(
            "organization", org_id, skip, limit
        )
        return {"logs": logs, "total": total, "skip": skip, "limit": limit}

    async def get_user_audit_logs(
        self, target_user_id: uuid.UUID, skip: int = 0, limit: int = 50
    ) -> dict[str, Any]:
        logs, total = await self.audit_service.get_target_audit_logs(
            "user", target_user_id, skip, limit
        )
        return {"logs": logs, "total": total, "skip": skip, "limit": limit}

    async def get_recent_audit_logs(self, limit: int = 100) -> dict[str, Any]:
        logs = await self.audit_service.get_recent_audit_logs(limit)
        return {"logs": logs, "count": len(logs)}


_resource_permission_controller_instance: ResourcePermissionController | None = None


def get_resource_permission_controller() -> ResourcePermissionController:
    """Get the resource permission controller singleton."""
    global _resource_permission_controller_instance
    if _resource_permission_controller_instance is None:
        _resource_permission_controller_instance = ResourcePermissionController()
    return _resource_permission_controller_instance
