"""Repository for permission audit logs."""

import uuid
from typing import Any

from sqlalchemy import func, select

from src.core.database.models import PermissionAuditModel

from .base_repository import BaseRepository


class PermissionAuditRepository(BaseRepository):
    """CRUD operations for permission audit logs."""

    async def create(
        self,
        action: str,
        resource_type: str,
        resource_id: str,
        resource_name: str,
        target_type: str,
        target_id: uuid.UUID,
        target_name: str,
        permission_level: str | None = None,
        old_permission_level: str | None = None,
        performed_by: uuid.UUID | None = None,
        permission_id: uuid.UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        details: dict | None = None,
    ) -> dict[str, Any]:
        """Create audit log entry."""
        async with self._session() as session:
            log = PermissionAuditModel(
                action=action,
                permission_id=permission_id,
                resource_type=resource_type,
                resource_id=resource_id,
                resource_name=resource_name,
                target_type=target_type,
                target_id=target_id,
                target_name=target_name,
                permission_level=permission_level,
                old_permission_level=old_permission_level,
                performed_by=performed_by,
                ip_address=ip_address,
                user_agent=user_agent,
                details=details or {},
            )
            session.add(log)
            await session.flush()
            await session.refresh(log)
            return self._to_dict(log)

    async def get_by_resource(
        self,
        resource_type: str,
        resource_id: str,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        """Get audit logs for a resource."""
        async with self._session() as session:
            query = select(PermissionAuditModel).where(
                PermissionAuditModel.resource_type == resource_type,
                PermissionAuditModel.resource_id == resource_id,
            )
            count_query = select(func.count(PermissionAuditModel.id)).where(
                PermissionAuditModel.resource_type == resource_type,
                PermissionAuditModel.resource_id == resource_id,
            )

            count_result = await session.execute(count_query)
            total = count_result.scalar_one()

            query = query.order_by(PermissionAuditModel.performed_at.desc())
            query = query.offset(skip).limit(limit)

            result = await session.execute(query)
            logs = result.scalars().all()

            return [self._to_dict(log) for log in logs], total

    async def get_by_target(
        self,
        target_type: str,
        target_id: uuid.UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        """Get audit logs for a target (organization or user)."""
        async with self._session() as session:
            query = select(PermissionAuditModel).where(
                PermissionAuditModel.target_type == target_type,
                PermissionAuditModel.target_id == target_id,
            )
            count_query = select(func.count(PermissionAuditModel.id)).where(
                PermissionAuditModel.target_type == target_type,
                PermissionAuditModel.target_id == target_id,
            )

            count_result = await session.execute(count_query)
            total = count_result.scalar_one()

            query = query.order_by(PermissionAuditModel.performed_at.desc())
            query = query.offset(skip).limit(limit)

            result = await session.execute(query)
            logs = result.scalars().all()

            return [self._to_dict(log) for log in logs], total

    async def get_by_performer(
        self,
        performed_by: uuid.UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        """Get audit logs performed by a user."""
        async with self._session() as session:
            query = select(PermissionAuditModel).where(
                PermissionAuditModel.performed_by == performed_by
            )
            count_query = select(func.count(PermissionAuditModel.id)).where(
                PermissionAuditModel.performed_by == performed_by
            )

            count_result = await session.execute(count_query)
            total = count_result.scalar_one()

            query = query.order_by(PermissionAuditModel.performed_at.desc())
            query = query.offset(skip).limit(limit)

            result = await session.execute(query)
            logs = result.scalars().all()

            return [self._to_dict(log) for log in logs], total

    async def get_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get recent audit logs."""
        async with self._session() as session:
            result = await session.execute(
                select(PermissionAuditModel)
                .order_by(PermissionAuditModel.performed_at.desc())
                .limit(limit)
            )
            return [self._to_dict(log) for log in result.scalars().all()]

    def _to_dict(self, log: PermissionAuditModel) -> dict[str, Any]:
        """Convert model to dict."""
        return {
            "id": log.id,
            "action": log.action,
            "permission_id": log.permission_id,
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "resource_name": log.resource_name,
            "target_type": log.target_type,
            "target_id": log.target_id,
            "target_name": log.target_name,
            "permission_level": log.permission_level,
            "old_permission_level": log.old_permission_level,
            "performed_by": log.performed_by,
            "performed_at": log.performed_at.isoformat() if log.performed_at else None,
            "ip_address": log.ip_address,
            "user_agent": log.user_agent,
            "details": log.details,
        }
