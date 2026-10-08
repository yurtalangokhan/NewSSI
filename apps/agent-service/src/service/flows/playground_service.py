"""Flow playground execution and streaming service.

Orchestrates flow validation, compilation, and playground streaming execution
under the service layer.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
import uuid
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from localization import t
from pydantic import ValidationError

from agents.implementations.flow_agent import FlowAgent
from core.exceptions import BadRequestError
from core.observability.logger import get_logger
from infrastructure.db.persistence_gateway import agent_definition_repository
from schemas.agent_config_policy import sanitize_client_agent_config
from schemas.flows import FlowSpec
from service.chat.message_conversion import convert_input_messages
from service.flow_model.migrations import migrate_spec
from service.flow_model.validator import validate
from service.flows.audit import get_flow_audit_emitter
from service.runtime.store_service import add_thread

logger = get_logger(__name__)


async def stream_flow_playground(
    *,
    flow_spec_raw: Any,
    definition_label: str,
    audit_target: UUID | str,
    version_no: int | None,
    request_obj: Any,
    user: Any,
    thread_namespace: str,
    service: Any = None,
) -> AsyncIterator[bytes | str]:
    """Execute and stream flow playground run."""
    svc = service
    agent_def_repo = agent_definition_repository()

    # 1. Validate the spec before compiling it
    try:
        flow_spec = FlowSpec.model_validate(flow_spec_raw)
    except ValidationError as exc:
        raise BadRequestError(
            message=t("flow.draft_spec_malformed", error=str(exc)),
        ) from exc

    flow_spec = migrate_spec(flow_spec)
    validation = validate(flow_spec)
    if not validation.valid:
        raise BadRequestError(
            code="flow.validation_failed",
            message="Flow failed validation.",
            details={"errors": [issue.to_dict() for issue in validation.errors]},
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
    thread_id = str(uuid.uuid5(uuid.NAMESPACE_URL, thread_namespace))

    try:
        await add_thread(
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
    stream_mode = ["values", "updates", "custom"] if request_obj.stream_tokens else ["values", "updates"]

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
            if (hasattr(node, "id") and node.id) or (isinstance(node, dict) and node.get("id"))
        ],
    }
    if request_obj.model:
        resolved_config["model"] = request_obj.model
    resolved_config.update(sanitize_client_agent_config(request_obj.agent_config))

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

    # The caller owns the transport: this returns the event stream itself so
    # the route decides it is server-sent events, and a non-HTTP caller can
    # consume the same run.
    return svc.event_generator(agent, input_messages, config, thread_id, run_id, stream_mode, user_id)
