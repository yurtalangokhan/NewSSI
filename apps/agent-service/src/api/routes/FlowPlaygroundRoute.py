"""Flow playground execution endpoint (P7 Task 41).

Endpoints:
  POST /agent-definitions/{definition_id}/flow/playground/runs/stream - execute a draft flow in the playground namespace
  POST /agent-definitions/flow/playground/runs/stream - execute a flow spec that has never been saved (inline)

Guards:
  flow:execute AND flow:update
"""

from __future__ import annotations

import uuid
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, ValidationError

from api.dependencies import AuthenticatedUser, require_permission
from api.routes.RunRoute import _get_controller
from core.logger import get_logger
from domain.flows.audit import get_flow_audit_emitter
from domain.flows.validator import validate
from models.flows import FlowSpec
from service.message_conversion import convert_input_messages

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
    from agents.flow_agent import FlowAgent
    from core.db.repositories.thread_repo import ThreadRepository
    from repository.agent_definition_repository import AgentDefinitionRepository

    agent_def_repo = AgentDefinitionRepository()
    thread_repo = ThreadRepository()

    # 1. Validate the spec before compiling it. A structurally broken draft
    # (e.g. an entry→exit path that only runs through resource nodes) would
    # otherwise compile into a dead-end graph that silently echoes the input
    # back — the exact failure mode bugfix #2 closed for publish. Structural
    # checks only: publish additionally runs the I/O-bound resource-existence
    # checks; the playground fails fast on shape, before any thread or audit
    # side effects. Same error shape as POST /flow/publish so the canvas can
    # highlight the offending nodes either way.
    try:
        flow_spec = FlowSpec.model_validate(flow_spec_raw)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Draft flow spec is malformed: {exc}",
        ) from exc
    # Migrate on read before validating, exactly like save/publish and the
    # compiler: a spec authored against an older template version (e.g. a v1
    # Router or the pre-Phase-3 counter Loop) must validate against its
    # current, migrated shape.
    from domain.flows.migrations import migrate_spec

    flow_spec = migrate_spec(flow_spec)
    validation = validate(flow_spec)
    if not validation.valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "flow.validation_failed",
                "message": "Flow failed validation.",
                "details": {"errors": [issue.to_dict() for issue in validation.errors]},
            },
        )

    # 2. Build fresh, uncached FlowAgent from the spec
    agent = FlowAgent(
        flow_spec,
        definition_id=definition_label,
        repository=agent_def_repo,
    )
    await agent.load()

    # 3. Create or resolve playground thread
    user_id = str(user.user_id) if hasattr(user, "user_id") else "unknown"
    # thread.thread_id is a UUID primary key — a raw namespace string cannot be
    # persisted (asyncpg DataError). A deterministic uuid5 keeps one stable
    # playground thread per namespace while satisfying the column type.
    thread_id = str(uuid.uuid5(uuid.NAMESPACE_URL, thread_namespace))

    try:
        await thread_repo.add_thread(
            {
                "thread_id": thread_id,
                "run_kind": "playground",
                "metadata": {
                    "user_id": user_id,
                    "definition_id": definition_label,
                    "run_kind": "playground",
                    "playground_namespace": thread_namespace,
                },
            }
        )
    except Exception as exc:
        logger.warning("Could not persist playground thread %s: %s", thread_id, exc)

    # 4. Prepare input messages and stream mode
    raw_input = request_obj.input or {}
    if isinstance(raw_input, dict):
        raw_messages = raw_input.get("messages", [])
    elif isinstance(raw_input, list):
        raw_messages = raw_input
    else:
        raw_messages = []

    if not raw_messages and request_obj.message:
        raw_messages = [{"role": "user", "content": request_obj.message}]

    input_messages = convert_input_messages(raw_messages)
    stream_mode = (
        ["values", "updates", "custom"] if request_obj.stream_tokens else ["values", "updates"]
    )

    # 5. Build RunnableConfig with tags and metadata
    resolved_config: dict[str, Any] = {
        "thread_id": thread_id,
        "user_id": user_id,
        "run_kind": "playground",
        "definition_id": definition_label,
        "flow_version_no": version_no,
        "stages": [
            {"name": node.id if hasattr(node, "id") else node.get("id")}
            for node in (
                flow_spec_raw.nodes
                if hasattr(flow_spec_raw, "nodes")
                else flow_spec_raw.get("nodes", [])
                if isinstance(flow_spec_raw, dict)
                else []
            )
            if (hasattr(node, "id") and getattr(node, "id"))
            or (isinstance(node, dict) and node.get("id"))
        ],
    }
    if request_obj.model:
        resolved_config["model"] = request_obj.model
    if request_obj.agent_config:
        resolved_config.update(request_obj.agent_config)

    tags = ["run_kind:playground"]
    if request_obj.stream_tokens:
        tags.append("stream-tokens")

    config = RunnableConfig(
        configurable=resolved_config,
        tags=tags,
        metadata={
            "definition_id": definition_label,
            "flow_version_no": version_no,
            "run_kind": "playground",
        },
    )

    run_id = str(uuid.uuid4())
    ctrl = _get_controller()

    # 6. Emit audit event
    audit_emitter = get_flow_audit_emitter()
    await audit_emitter.emit(
        "flow:playground_run",
        audit_target,
        user=user,
        details={
            "run_kind": "playground",
            "thread_id": thread_id,
            "thread_namespace": thread_namespace,
            "version_no": version_no,
        },
    )

    event_gen = ctrl.event_generator(
        agent, input_messages, config, thread_id, run_id, stream_mode, user_id
    )

    return StreamingResponse(event_gen, media_type="text/event-stream")


@router.post(
    "/{definition_id}/flow/playground/runs/stream",
    response_class=StreamingResponse,
)
async def run_flow_playground_stream(
    definition_id: UUID,
    request_obj: FlowPlaygroundRunRequest,
    user: AuthenticatedUser = Depends(_require_execute),
    _update_guard: AuthenticatedUser = Depends(_require_update),
) -> StreamingResponse:
    from repository.flow_version_repository import FlowVersionRepository

    flow_version_repo = FlowVersionRepository()

    # Fetch draft (must exist; 404 if no draft)
    draft = await flow_version_repo.get_draft(definition_id)
    if not draft or not draft.flow_spec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No draft flow found for definition {definition_id}",
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
)
async def run_flow_playground_inline_stream(
    request_obj: FlowPlaygroundInlineRunRequest,
    user: AuthenticatedUser = Depends(_require_execute),
    _update_guard: AuthenticatedUser = Depends(_require_update),
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
