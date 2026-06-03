import uuid
from typing import Any

from src.repository import AuditLogRepository


class AuditService:
    def __init__(self):
        self.repo = AuditLogRepository()

    async def log(
        self,
        action: str,
        resource: str,
        user_id: uuid.UUID | None = None,
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        log_entry = await self.repo.create(
            action=action,
            resource=resource,
            user_id=user_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return {
            "id": str(log_entry.id),
            "action": log_entry.action,
            "resource": log_entry.resource,
            "user_id": str(log_entry.user_id) if log_entry.user_id else None,
            "created_at": log_entry.created_at.isoformat(),
        }

    async def list_by_user(
        self, user_id: uuid.UUID, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        logs = await self.repo.list_by_user(user_id, limit, offset)
        return self._logs_to_dicts(logs)

    async def list_recent(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        logs = await self.repo.list_recent(limit, offset)
        return self._logs_to_dicts(logs)

    def _logs_to_dicts(self, logs) -> list[dict[str, Any]]:
        return [
            {
                "id": str(log.id),
                "action": log.action,
                "resource": log.resource,
                "user_id": str(log.user_id) if log.user_id else None,
                "details": log.details or {},
                "ip_address": log.ip_address,
                "user_agent": log.user_agent,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ]


_audit_service: AuditService | None = None


def get_audit_service() -> AuditService:
    global _audit_service
    if _audit_service is None:
        _audit_service = AuditService()
    return _audit_service
