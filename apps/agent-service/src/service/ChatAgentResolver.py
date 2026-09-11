"""Choosing which agent answers a chat turn.

Split out of ``api/routes/ChatRoute.send_chat_message``. Mapping a persona id
onto a registered agent — builtin, custom, or a published flow — is domain
routing, so the unpublished-flow refusal leaves here as
``FlowNotPublishedError`` and the route turns it into 409.

Behaviour is unchanged from the extracted original.
"""

from __future__ import annotations

import uuid
from typing import Any

from agents import DEFAULT_AGENT
from controller.session_controller import PERSONA_ID_TO_AGENT
from core.logger import get_logger

logger = get_logger(__name__)


def _resolve_custom_persona_agent(
    persona_id: int,
    custom_persona: dict[str, Any],
    llm_override: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    """Resolve a custom persona to the execution id and runtime overrides."""
    base_agent = custom_persona.get("base_agent")
    assistant_id = str(persona_id) if base_agent == "dynamic-agent" else base_agent or DEFAULT_AGENT

    resolved_override = dict(llm_override or {})
    if custom_persona.get("system_prompt"):
        resolved_override["system_prompt"] = custom_persona["system_prompt"]
    if custom_persona.get("mcp_tools"):
        resolved_override["mcp_tools"] = custom_persona["mcp_tools"]
    if custom_persona.get("rag_config"):
        resolved_override["rag_config"] = custom_persona["rag_config"]

    # Connector access is derived from the selected saved persona. A request
    # payload may carry stale editor state, but it must never grant runtime
    # access to a connection that is not currently assigned to this persona.
    resolved_override["connector_bindings"] = list(custom_persona.get("connector_bindings") or [])
    binding_references = dict(resolved_override.get("binding_references") or {})
    binding_references["connectors.persona_id"] = str(persona_id)
    resolved_override["binding_references"] = binding_references

    # Pass the numeric persona_id so _handle_input reads LTM settings from the
    # correct persona, not from the underlying builtin graph key.
    resolved_override["_persona_id"] = persona_id
    return assistant_id, resolved_override


async def resolve_chat_agent(
    persona_id: Any,
    llm_override: dict[str, Any] | None,
) -> tuple[str, dict[str, Any] | None]:
    """Return the agent id for this turn, plus the override it implies.

    A custom persona can carry its own model settings, which is why the
    override comes back alongside the id rather than being resolved
    separately.

    Raises:
        FlowNotPublishedError: the persona is a flow with nothing published.
            Refusing here matters — a half-open SSE stream that dies on the
            first token gives the client no status code to act on.
    """
    assistant_id = DEFAULT_AGENT

    if persona_id:
        if isinstance(persona_id, str):
            try:
                uuid.UUID(persona_id)
                assistant_id = persona_id
            except (ValueError, AttributeError):
                assistant_id = DEFAULT_AGENT
        else:
            assistant_id = PERSONA_ID_TO_AGENT.get(persona_id, DEFAULT_AGENT)

    if persona_id is not None and not isinstance(persona_id, str):
        from repository.persona_repository import PersonaDB

        try:
            custom_persona = await PersonaDB.get(persona_id)
        except Exception:
            custom_persona = None

        if custom_persona and not custom_persona.get("is_builtin"):
            assistant_id, llm_override = _resolve_custom_persona_agent(
                persona_id,
                custom_persona,
                llm_override,
            )
            if llm_override.get("connector_bindings"):
                from service.ConnectorToolService import get_connector_tool_service

                llm_override[
                    "connector_bindings"
                ] = await get_connector_tool_service().describe_bindings(
                    llm_override["connector_bindings"]
                )

            # An unpublished flow has no graph to run. Refuse before any
            # streaming starts so the client gets a status code, not a
            # half-open SSE stream that dies on the first token.
            from domain.flows.gating import assert_flow_chat_ready

            await assert_flow_chat_ready(persona_id)

    return str(assistant_id), llm_override
