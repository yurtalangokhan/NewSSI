"""Pure helpers for flow routes.

Extracted from ``flow_versions_route`` and ``flow_playground_route`` to keep routes
lean and maintainable.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi.responses import StreamingResponse

from core.observability.logger import get_logger
from service.auth.auth_service import AuthenticatedUser
from service.stream.error_events import guard_stream

logger = get_logger(__name__)


def version_to_dict(version: Any) -> dict[str, Any]:
    """Serialize a FlowVersion entity to a response dict."""
    return {
        "id": str(version.id),
        "definition_id": str(version.definition_id),
        "version_no": version.version_no,
        "status": version.status,
        "created_by": version.created_by,
        "published_by": version.published_by,
        "created_at": version.created_at.isoformat() if version.created_at else None,
        "published_at": version.published_at.isoformat() if version.published_at else None,
        "notes": version.notes,
    }


async def stream_flow_playground(
    *,
    flow_spec_raw: Any,
    definition_label: str,
    audit_target: UUID | str,
    version_no: int | None,
    request_obj: Any,
    user: AuthenticatedUser,
    thread_namespace: str,
    service: Any = None,
) -> StreamingResponse:
    """Run the flow playground and wrap its event stream as server-sent events.

    The service returns the event stream; choosing the transport for it is this
    layer's job.
    """
    from service.flows.playground_service import stream_flow_playground as _stream_svc

    event_stream = await _stream_svc(
        flow_spec_raw=flow_spec_raw,
        definition_label=definition_label,
        audit_target=audit_target,
        version_no=version_no,
        request_obj=request_obj,
        user=user,
        thread_namespace=thread_namespace,
        service=service,
    )
    return StreamingResponse(guard_stream(event_stream), media_type="text/event-stream")
