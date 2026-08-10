"""Permission audit log service."""

import uuid
from typing import Any

from src.repository import PermissionAuditRepository


class PermissionAuditService:
    """Business logic for permission audit logs."""

    def __init__(self):
        self.repo = PermissionAuditRepository()

    async def get_resource_audit_logs(
        self,
        resource_type: str,
        resource_id: str,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        """Get audit logs for a specific resource."""
        return await self.repo.get_by_resource(resource_type, resource_id, skip, limit)

    async def get_target_audit_logs(
        self,
        target_type: str,
        target_id: uuid.UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        """Get audit logs for a target (organization or user)."""
        if target_type not in ("organization", "user"):
            raise ValueError("target_type must be 'organization' or 'user'")

        return await self.repo.get_by_target(target_type, target_id, skip, limit)

    async def get_user_audit_logs(
        self,
        performed_by: uuid.UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        """Get audit logs performed by a specific user."""
        return await self.repo.get_by_performer(performed_by, skip, limit)

    async def get_recent_audit_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get most recent audit logs across all resources."""
        return await self.repo.get_recent(limit)


# Singleton instance
_permission_audit_service_instance: PermissionAuditService | None = None


def get_permission_audit_service() -> PermissionAuditService:
    """Get singleton permission audit service instance."""
    global _permission_audit_service_instance
    if _permission_audit_service_instance is None:
        _permission_audit_service_instance = PermissionAuditService()
    return _permission_audit_service_instance
