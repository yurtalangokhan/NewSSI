"""Per-run bridge from a ToolMessage artifact to a hydrated evidence packet."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from service.knowledge_evidence.hydrator import KnowledgeEvidenceHydrator
from service.knowledge_evidence.packets import knowledge_tool_delta
from service.knowledge_evidence.references import evidence_id_from_artifact


class KnowledgeEvidencePresenter:
    """Owned by one streaming run; knows the run's thread."""

    def __init__(self, hydrator: KnowledgeEvidenceHydrator, *, thread_id: str | None) -> None:
        self._hydrator = hydrator
        self._thread_id = thread_id

    async def tool_result_packet(self, *, tool_name: str, call_id: str | None, artifact: Any) -> dict[str, Any] | None:
        """The knowledge delta for this tool result, or ``None`` if it carries no evidence."""
        evidence_id = evidence_id_from_artifact(artifact)
        if evidence_id is None:
            return None
        return await self.evidence_packet(tool_name=tool_name, call_id=call_id, evidence_id=evidence_id)

    async def evidence_packet(self, *, tool_name: str, call_id: str | None, evidence_id: UUID) -> dict[str, Any]:
        """The hydrated knowledge delta for an evidence row of this run's thread."""
        packet = knowledge_tool_delta(tool_name=tool_name, call_id=call_id, evidence_id=evidence_id)
        await self._hydrator.hydrate(self._thread_id, [packet])
        return packet
