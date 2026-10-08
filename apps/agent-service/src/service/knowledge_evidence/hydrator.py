"""Fill knowledge packets with their evidence, reading only the owning thread."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from core.observability.logger import get_logger
from service.knowledge_evidence.packets import unhydrated_evidence_id
from service.knowledge_evidence.ports import EvidenceStore
from service.knowledge_evidence.references import parse_uuid

logger = get_logger(__name__)


class KnowledgeEvidenceHydrator:
    """Sets ``data`` on knowledge packets, in place, with one batched read.

    Evidence is looked up only among ``thread_id``'s rows, so an id copied from
    another thread resolves to nothing. A missing row or a failed read leaves
    ``data`` as ``None``; the client renders that as "details unavailable".
    """

    def __init__(self, store: EvidenceStore) -> None:
        self._store = store

    async def hydrate(self, thread_id: UUID | str | None, packets: Iterable[Any]) -> None:
        pending = [(packet, evidence_id) for packet in packets if (evidence_id := unhydrated_evidence_id(packet))]
        owner = parse_uuid(thread_id)
        if not pending or owner is None:
            return
        try:
            found = await self._store.get_many(owner, {evidence_id for _, evidence_id in pending})
        except Exception:
            logger.warning("Could not load knowledge evidence for thread %s", owner, exc_info=True)
            return
        for packet, evidence_id in pending:
            evidence = found.get(evidence_id)
            if evidence is not None:
                packet["data"] = evidence.model_dump(mode="json")

    async def hydrate_tree(self, thread_id: UUID | str | None, packets_2d: Iterable[Iterable[Any]]) -> None:
        """``hydrate`` for reconstructed history: ``{"placement", "obj"}`` per turn."""
        objs = [packet.get("obj") for turn in packets_2d for packet in turn if isinstance(packet, dict)]
        await self.hydrate(thread_id, objs)
