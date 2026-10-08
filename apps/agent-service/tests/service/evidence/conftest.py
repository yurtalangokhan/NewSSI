"""Shared fakes for knowledge evidence tests."""

from __future__ import annotations

from collections.abc import Collection
from uuid import UUID, uuid4

import pytest
from schemas.knowledge_evidence import EvidenceKind, KnowledgeEvidence

THREAD_ID = UUID("7f7d8c1e-5e4b-4a57-9c1d-2f6f0d4b9a10")


def make_evidence(query: str = "leave carry-over", *, tool: str = "database_search") -> KnowledgeEvidence:
    return KnowledgeEvidence(
        kind=EvidenceKind.DOCUMENT,
        tool=tool,
        query=query,
        chunks=[{"ref": 1, "content": "Unused leave carries over.", "source": {"document": "a.pdf"}}],
        model_context="[1] (a.pdf)\nUnused leave carries over.",
    )


class InMemoryEvidenceStore:
    """EvidenceStore double keeping rows per thread, like the real table."""

    def __init__(self) -> None:
        self.rows: dict[UUID, tuple[UUID, KnowledgeEvidence]] = {}
        self.fail_with: Exception | None = None

    async def add(self, thread_id: UUID, evidence: KnowledgeEvidence) -> UUID:
        if self.fail_with is not None:
            raise self.fail_with
        evidence_id = uuid4()
        self.rows[evidence_id] = (thread_id, evidence)
        return evidence_id

    async def get_many(self, thread_id: UUID, evidence_ids: Collection[UUID]) -> dict[UUID, KnowledgeEvidence]:
        if self.fail_with is not None:
            raise self.fail_with
        return {
            evidence_id: evidence
            for evidence_id, (owner, evidence) in self.rows.items()
            if owner == thread_id and evidence_id in set(evidence_ids)
        }


@pytest.fixture
def store() -> InMemoryEvidenceStore:
    return InMemoryEvidenceStore()
