"""Repository for ``knowledge_evidence`` rows.

Every read is scoped by thread: an evidence id taken from one thread's
checkpoint can never load another thread's row.
"""

from __future__ import annotations

from collections.abc import Collection
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import select

from core.observability.logger import get_logger
from infrastructure.db.models.knowledge_evidence import KnowledgeEvidenceModel
from infrastructure.db.repositories.base import BaseRepository
from schemas.knowledge_evidence import KnowledgeEvidence

logger = get_logger(__name__)


class KnowledgeEvidenceRepository(BaseRepository):
    """Append-only store of the evidence each retrieval call produced."""

    async def add(self, thread_id: UUID, evidence: KnowledgeEvidence) -> UUID:
        """Persist ``evidence`` under ``thread_id`` and return its new id."""
        evidence_id = uuid4()
        async with self._session() as session:
            session.add(
                KnowledgeEvidenceModel(
                    id=evidence_id,
                    thread_id=thread_id,
                    kind=evidence.kind.value,
                    tool=evidence.tool,
                    schema_version=evidence.schema_version,
                    payload=evidence.model_dump(mode="json"),
                )
            )
            await session.flush()
        return evidence_id

    async def get_many(self, thread_id: UUID, evidence_ids: Collection[UUID]) -> dict[UUID, KnowledgeEvidence]:
        """The thread's evidence among ``evidence_ids``; unknown ids are absent."""
        if not evidence_ids:
            return {}
        statement = select(KnowledgeEvidenceModel.id, KnowledgeEvidenceModel.payload).where(
            KnowledgeEvidenceModel.thread_id == thread_id,
            KnowledgeEvidenceModel.id.in_(list(evidence_ids)),
        )
        async with self._read_session() as session:
            rows = (await session.execute(statement)).all()

        found: dict[UUID, KnowledgeEvidence] = {}
        for evidence_id, payload in rows:
            try:
                found[evidence_id] = KnowledgeEvidence.model_validate(payload)
            except ValidationError:
                logger.warning("Skipping knowledge evidence %s: payload no longer valid", evidence_id)
        return found
