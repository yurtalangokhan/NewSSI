"""Timeline packets that carry knowledge evidence.

Evidence rides the existing ``custom_tool_*`` packets so turn grouping, stage
tagging, and reconstruction treat it like any other tool step. Packets are
built with ``data=None`` and filled by ``KnowledgeEvidenceHydrator``, the one
path shared by the live stream and reloaded history.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from service.knowledge_evidence.references import KNOWLEDGE_RESPONSE_TYPE, parse_uuid


def knowledge_tool_delta(*, tool_name: str, call_id: str | None, evidence_id: UUID) -> dict[str, Any]:
    """A tool-result packet referencing ``evidence_id``; ``data`` awaits hydration."""
    return {
        "type": "custom_tool_delta",
        "tool_name": tool_name,
        "response_type": KNOWLEDGE_RESPONSE_TYPE,
        "evidence_id": str(evidence_id),
        "data": None,
        "call_id": call_id,
    }


def unhydrated_evidence_id(packet: Any) -> UUID | None:
    """The evidence id of a knowledge packet whose data is still missing."""
    if not isinstance(packet, dict):
        return None
    if packet.get("response_type") != KNOWLEDGE_RESPONSE_TYPE or packet.get("data") is not None:
        return None
    return parse_uuid(packet.get("evidence_id"))
