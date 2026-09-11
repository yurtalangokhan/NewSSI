"""The single place that decides which agent class an AgentDefinition becomes.

Three existing call sites each used to construct DynamicAgent directly:
service/AgentHelpers.py, service/AssistantAgentService.py, and (indirectly,
via an isinstance check) api/routes/AgentsRoute.py. FlowAgent is a sibling
class to DynamicAgent (design spec section 6.2), not a subclass, so every
one of those sites needs the same "graph_schema == 'flow' ?" branch. This
module is that branch, written once.
"""

from __future__ import annotations

from typing import Any

from agents.dynamic_agent import DynamicAgent
from agents.flow_agent import FlowAgent
from core.logger import get_logger

logger = get_logger(__name__)


async def _resolve_owner_user_id(definition: Any) -> str:
    """Owner id for a flow-backed agent.

    ``AgentDefinitionModel`` has no ``user_id`` column and ``created_by`` is
    never populated by the create path, so the reliable owner is the linked
    persona's ``user_id`` (the same link ``has_active_bindings`` uses). Falls
    back to ``created_by`` and finally to ``""`` — an ownerless flow simply
    cannot send mail, which is the safe outcome.
    """
    persona_id = getattr(definition, "persona_id", None)
    if persona_id is not None:
        try:
            from service.persistence_gateway import persona_db

            persona = await persona_db().get(persona_id)
            if persona and persona.get("user_id"):
                return str(persona["user_id"])
        except Exception as exc:  # noqa: BLE001 - never block agent construction
            logger.warning("Could not resolve flow owner from persona %s: %s", persona_id, exc)
    return str(
        getattr(definition, "user_id", None) or getattr(definition, "created_by", None) or ""
    )


async def _resolve_published_version_no(definition: Any) -> int | None:
    """The version_no of the flow this definition currently publishes, or
    None if nothing is published yet (or the lookup fails — an unknown
    version just means the chat strip falls back to the live published
    flow, never a broken run)."""
    if getattr(definition, "published_flow_version_id", None) is None:
        return None
    try:
        from service.persistence_gateway import flow_version_repository

        published = await flow_version_repository().get_published(definition.id)
        return getattr(published, "version_no", None) if published else None
    except Exception as exc:  # noqa: BLE001 - never block agent construction
        logger.warning("Could not resolve published flow version for %s: %s", definition.id, exc)
        return None


async def create_agent_for_definition(
    definition: Any,
    *,
    checkpointer: Any | None = None,
) -> DynamicAgent | FlowAgent:
    """Construct the right agent class for one AgentDefinitionModel.

    A flow-backed definition becomes a FlowAgent here; everything else is
    resolved through ``AgentFactory`` (ASC-5), which validates the definition,
    assembles the runtime via AgentComposer and hands back a loaded
    DynamicAgent.

    Does not cache — callers keep their existing cache-lookup pattern
    (get_cached_agent/cache_agent, keyed by definition id) around this call,
    unchanged from before this factory existed.
    """
    if getattr(definition, "graph_schema", None) == "flow":
        agent: DynamicAgent | FlowAgent = FlowAgent(
            definition.flow_spec,
            definition_id=str(definition.id),
            user_id=await _resolve_owner_user_id(definition),
            name_hint=getattr(definition, "name", None),
            flow_version_no=await _resolve_published_version_no(definition),
        )
        if checkpointer is not None:
            agent._checkpointer = checkpointer
        return agent

    from agent_composition.application.compose_agent import AgentFactory
    from service.persistence_gateway import agent_definition_repository

    return await AgentFactory.create(
        definition_config=definition.to_config(),
        checkpointer=checkpointer,
        repository=agent_definition_repository(),
    )


def invalidate_agent_cache_for(definition_id: str, graph_schema: str) -> None:
    """Evict a definition from whichever cache actually holds it.

    P2 Task 13 gave FlowAgent its own cache module, separate from
    DynamicAgent's — but domain/agents/service.py's update/delete paths kept
    calling agents.dynamic_agent.invalidate_agent_cache unconditionally
    (P3 finding: a flow-backed agent updated or deleted through
    AgentDefinitionService kept serving its previously-compiled graph, since
    that call clears an entry in the wrong cache dict). This is the single
    call site both paths should use so a third agent kind can't reintroduce
    the same gap.
    """
    if graph_schema == "flow":
        from agents.flow_agent import invalidate_agent_cache as invalidate_flow_cache

        invalidate_flow_cache(definition_id)
    else:
        from agents.dynamic_agent import invalidate_agent_cache as invalidate_dynamic_cache

        invalidate_dynamic_cache(definition_id)
