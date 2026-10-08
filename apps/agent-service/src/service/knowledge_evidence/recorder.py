"""Persist evidence without ever failing the retrieval that produced it."""

from __future__ import annotations

from uuid import UUID

from core.observability.logger import get_logger
from schemas.knowledge_evidence import KnowledgeEvidence
from service.knowledge_evidence.ports import EvidenceStore, ThreadIdProvider
from service.knowledge_evidence.thread_scope import current_thread_id

logger = get_logger(__name__)


class KnowledgeEvidenceRecorder:
    """Writes evidence under the current thread; a failure only loses the card."""

    def __init__(self, store: EvidenceStore, *, thread_id_provider: ThreadIdProvider = current_thread_id) -> None:
        self._store = store
        self._thread_id_provider = thread_id_provider

    async def record(self, evidence: KnowledgeEvidence, *, thread_id: UUID | None = None) -> UUID | None:
        """The new evidence id, or ``None`` when there is no thread or the write failed."""
        owner = thread_id or self._thread_id_provider()
        if owner is None:
            return None
        try:
            return await self._store.add(owner, evidence)
        except Exception:
            logger.warning("Could not record knowledge evidence for thread %s", owner, exc_info=True)
            return None
