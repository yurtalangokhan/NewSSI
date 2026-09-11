"""Chat-readiness gate for flow-backed personas.

Kept out of agent_factory: the factory builds an agent from a definition
that already exists, while this answers the earlier question of whether a
chat request may proceed at all. Callers pass their own repository in
tests; production resolves the default lazily to avoid an import cycle
between the routes and the storage layer.
"""

from __future__ import annotations

from typing import Any

from core.exceptions import FlowNotPublishedError
from core.logger import get_logger

logger = get_logger(__name__)


async def assert_flow_chat_ready(persona_id: int, *, repository: Any | None = None) -> None:
    """Raise FlowNotPublishedError if this persona is an unpublished flow.

    Non-flow personas, personas with no definition row, and lookup failures
    all pass: the gate only ever refuses a case it positively identified.
    """
    if repository is None:
        from service.persistence_gateway import agent_definition_repository

        repository = agent_definition_repository()

    try:
        definition = await repository.get_by_persona_id(persona_id)
    except Exception as exc:  # noqa: BLE001 - a lookup failure must not block chat
        logger.warning("Flow chat gate could not load definition for %s: %s", persona_id, exc)
        return

    if definition is None:
        return
    if getattr(definition, "graph_schema", None) != "flow":
        return
    if getattr(definition, "published_flow_version_id", None) is None:
        raise FlowNotPublishedError(persona_id)
