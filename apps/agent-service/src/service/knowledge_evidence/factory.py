"""Composition root for the knowledge evidence service."""

from __future__ import annotations

from infrastructure.db.persistence_gateway import knowledge_evidence_repository
from service.knowledge_evidence.artifact_policy import KnowledgeEvidenceArtifactPolicy
from service.knowledge_evidence.hydrator import KnowledgeEvidenceHydrator
from service.knowledge_evidence.presenter import KnowledgeEvidencePresenter
from service.knowledge_evidence.recorder import KnowledgeEvidenceRecorder


def build_knowledge_evidence_recorder() -> KnowledgeEvidenceRecorder:
    return KnowledgeEvidenceRecorder(knowledge_evidence_repository())


def build_knowledge_evidence_artifact_policy() -> KnowledgeEvidenceArtifactPolicy:
    return KnowledgeEvidenceArtifactPolicy(build_knowledge_evidence_recorder())


def build_knowledge_evidence_hydrator() -> KnowledgeEvidenceHydrator:
    return KnowledgeEvidenceHydrator(knowledge_evidence_repository())


def build_knowledge_evidence_presenter(thread_id: str | None) -> KnowledgeEvidencePresenter:
    return KnowledgeEvidencePresenter(build_knowledge_evidence_hydrator(), thread_id=thread_id)
