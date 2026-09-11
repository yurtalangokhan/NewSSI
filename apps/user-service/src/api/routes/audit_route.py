"""Internal audit-log write endpoint.

Lets other services (agent-service, for flow lifecycle events — P3 Task 19)
write into user-service's existing audit_logs table without duplicating
audit storage/retention/export logic in a second service. Guarded the same
way settings_route's internal endpoints are: a caller's own user JWT, or the
service-to-service X-Internal-Service-Token.

audit_logs.user_id is a real FK to users.id — a caller-supplied identifier
that isn't a valid UUID (or doesn't resolve to a real user, e.g. a Keycloak
subject the local users table has never seen, or the dev-mode placeholder
"dev-user") is treated as unknown rather than rejected: the event is still
recorded with user_id=NULL, and the raw identifier goes into details.actor_identity
instead so the record isn't lost.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends

from src.api.dependencies import require_auth_or_internal_service_token
from src.service.audit_service import get_audit_service

internal_router = APIRouter(prefix="/internal/audit-logs", tags=["audit"])


def _resolve_user_id(raw_user_id: str | None, details: dict[str, Any]) -> uuid.UUID | None:
    if not raw_user_id:
        return None
    try:
        return uuid.UUID(raw_user_id)
    except (TypeError, ValueError):
        details.setdefault("actor_identity", raw_user_id)
        return None


@internal_router.post("")
async def create_audit_log(
    body: Annotated[dict[str, Any], Body()],
    _authenticated: Annotated[str, Depends(require_auth_or_internal_service_token)],
) -> dict[str, Any]:
    details = dict(body.get("details") or {})
    resolved_user_id = _resolve_user_id(body.get("user_id"), details)

    return await get_audit_service().log(
        action=body["action"],
        resource=body["resource"],
        user_id=resolved_user_id,
        details=details,
    )
