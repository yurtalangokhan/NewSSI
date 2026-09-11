"""Flow lifecycle audit events (design spec 9.2, P3 Task 19).

Emits to user-service's existing audit_logs table via a new internal
endpoint — option B of the P3 planning decision (.tmp/flow-canvas-task-19-brief.md
"open decision"): agent-service has no audit infrastructure of its own, and
splitting the audit trail across two stores (a local agent-service table)
would defeat the point of a single trail an auditor already reads.

Emission happens from the route layer (FlowVersionsRoute.py,
AgentDefinitionsRoute.py), not from FlowService — only the route has the
full AuthenticatedUser (with .claims) needed for identity resolution;
FlowService's existing methods only ever received plain user-id strings
(Tasks 15-17), and changing those already-tested signatures for this would
have been a needless, unrelated risk. Always called *after* the state
change has committed, never inside its transaction.
"""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

from core.logger import get_logger

logger = get_logger(__name__)

DRAFT_UPDATE_COALESCE_SECONDS = 60.0


class FlowAuditEmitter:
    """Emits flow audit events. Never raises into the caller."""

    def __init__(self) -> None:
        self._last_draft_update_emit: dict[str, float] = {}

    async def emit(
        self,
        action: str,
        definition_id: UUID | str,
        *,
        user: Any,
        details: dict[str, Any] | None = None,
    ) -> None:
        from service.AuthService import resolve_user_service_id
        from service.UserServiceClient import create_audit_log

        resolved_details = dict(details or {})
        user_service_id = resolve_user_service_id(user)
        if user_service_id is None:
            resolved_details.setdefault("actor_identity", user.user_id)

        try:
            await create_audit_log(
                action,
                f"flow:{definition_id}",
                user_id=user_service_id,
                details=resolved_details,
                access_token=user.access_token,
            )
        except Exception:  # noqa: BLE001 - audit must never break the caller's operation
            logger.exception("Failed to emit flow audit event %s for %s", action, definition_id)

    def should_emit_draft_update(self, definition_id: str) -> bool:
        """Debounce flow:updated so autosave doesn't flood the audit trail.

        Emits at most once per definition per DRAFT_UPDATE_COALESCE_SECONDS
        — a full diff-per-keystroke would put the whole flow spec into
        audit_logs.details on every autosave for no benefit the version
        table (which already holds every draft state) doesn't provide.
        """
        now = time.monotonic()
        last = self._last_draft_update_emit.get(definition_id)
        if last is not None and now - last < DRAFT_UPDATE_COALESCE_SECONDS:
            return False
        self._last_draft_update_emit[definition_id] = now
        return True


_emitter: FlowAuditEmitter | None = None


def get_flow_audit_emitter() -> FlowAuditEmitter:
    global _emitter
    if _emitter is None:
        _emitter = FlowAuditEmitter()
    return _emitter
