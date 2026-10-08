"""Flow playground execution endpoint (P7 Task 41).

Endpoints:
  POST /agent-definitions/{definition_id}/flow/playground/runs/stream - execute a draft flow in the playground namespace
  POST /agent-definitions/flow/playground/runs/stream - execute a flow spec that has never been saved (inline)

Guards:
  flow:execute AND flow:update
"""

from __future__ import annotations

from typing import Annotated, Any
import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from localization import t
from pydantic import BaseModel

from api.dependencies import AuthenticatedUser, require_permission
from api.helpers.flow_helpers import stream_flow_playground
from core.observability.logger import get_logger
from service.runtime.run_service import get_run_service as _get_service

logger = get_logger(__name__)

router = APIRouter(prefix="/agent-definitions", tags=["flow-playground"])

_require_execute = require_permission("flow:execute")
_require_update = require_permission("flow:update")


class FlowPlaygroundRunRequest(BaseModel):
    input: dict[str, Any] | None = None
    message: str | None = None
    model: str | None = None
    stream_tokens: bool = True
    agent_config: dict[str, Any] | None = None


class FlowPlaygroundInlineRunRequest(FlowPlaygroundRunRequest):
    """Playground run for a flow that has never been saved — e.g. still on
    the "create agent" form, before an agent_definitions row exists. The
    graph travels in the request body instead of being looked up by id,
    mirroring Langflow's own build endpoint (vendor/langflow/utils/buildUtils.ts),
    which posts the canvas's in-memory nodes/edges directly rather than
    requiring a persisted Flow row first."""

    flow_spec: dict[str, Any]
    session_id: str | None = None


async def _stream_flow_playground(
    *,
    flow_spec_raw: Any,
    definition_label: str,
    audit_target: UUID | str,
    version_no: int | None,
    request_obj: FlowPlaygroundRunRequest,
    user: AuthenticatedUser,
    thread_namespace: str,
) -> StreamingResponse:
    return await stream_flow_playground(
        flow_spec_raw=flow_spec_raw,
        definition_label=definition_label,
        audit_target=audit_target,
        version_no=version_no,
        request_obj=request_obj,
        user=user,
        thread_namespace=thread_namespace,
        service=_get_service(),
    )


@router.post(
    "/{definition_id}/flow/playground/runs/stream",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
            "description": "Stream of flow execution events",
        }
    },
)
async def run_flow_playground_stream(
    definition_id: UUID,
    request_obj: FlowPlaygroundRunRequest,
    user: Annotated[AuthenticatedUser, Depends(_require_execute)],
    _update_guard: Annotated[AuthenticatedUser, Depends(_require_update)],
) -> StreamingResponse:
    from service.flows.service import FlowService

    # Fetch draft (must exist; 404 if no draft)
    draft = await FlowService().get_draft(definition_id)
    if not draft or not draft.flow_spec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=t("flow.draft_not_found_for_definition", definition_id=definition_id),
        )

    user_id = str(user.user_id) if hasattr(user, "user_id") else "unknown"
    namespace = f"playground:{definition_id}:{user_id}"

    return await _stream_flow_playground(
        flow_spec_raw=draft.flow_spec,
        definition_label=str(definition_id),
        audit_target=definition_id,
        version_no=draft.version_no,
        request_obj=request_obj,
        user=user,
        thread_namespace=namespace,
    )


@router.post(
    "/flow/playground/runs/stream",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
            "description": "Stream of inline flow execution events",
        }
    },
)
async def run_flow_playground_inline_stream(
    request_obj: FlowPlaygroundInlineRunRequest,
    user: Annotated[AuthenticatedUser, Depends(_require_execute)],
    _update_guard: Annotated[AuthenticatedUser, Depends(_require_update)],
) -> StreamingResponse:
    """Same as ``run_flow_playground_stream`` but for a flow that has never
    been saved — the graph comes from the request body, not a DB draft."""
    user_id = str(user.user_id) if hasattr(user, "user_id") else "unknown"
    session_id = request_obj.session_id or str(uuid.uuid4())
    label = f"inline:{session_id}"
    namespace = f"playground:{label}:{user_id}"

    return await _stream_flow_playground(
        flow_spec_raw=request_obj.flow_spec,
        definition_label=label,
        audit_target=label,
        version_no=None,
        request_obj=request_obj,
        user=user,
        thread_namespace=namespace,
    )
