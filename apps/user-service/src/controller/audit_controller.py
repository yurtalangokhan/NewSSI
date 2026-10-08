"""Orchestrate audit writes without resolving live historical identities."""

import uuid

from src.schema.audit import AuditLogRequest
from src.service.audit_service import get_audit_service


class AuditController:
    async def create_log(self, payload: AuditLogRequest) -> dict:
        details = dict(payload.details or {})
        actor_id = None
        if payload.user_id:
            try:
                actor_id = uuid.UUID(payload.user_id)
            except ValueError:
                details.setdefault("actor_identity", payload.user_id)
        return await get_audit_service().log(
            action=payload.action,
            resource=payload.resource,
            user_id=actor_id,
            details=details,
        )


def get_audit_controller() -> AuditController:
    return AuditController()
