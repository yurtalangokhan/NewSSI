"""Ports the knowledge evidence service depends on."""

from __future__ import annotations

from collections.abc import Callable, Collection
from typing import Protocol
from uuid import UUID

from schemas.knowledge_evidence import KnowledgeEvidence


class EvidenceStore(Protocol):
    """Thread-scoped persistence for evidence payloads."""

    async def add(self, thread_id: UUID, evidence: KnowledgeEvidence) -> UUID: ...

    async def get_many(self, thread_id: UUID, evidence_ids: Collection[UUID]) -> dict[UUID, KnowledgeEvidence]: ...


#: Resolves the thread the current call belongs to, or ``None`` outside a thread.
ThreadIdProvider = Callable[[], UUID | None]
