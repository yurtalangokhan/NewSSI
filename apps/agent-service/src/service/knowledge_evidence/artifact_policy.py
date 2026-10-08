"""Turn a tool's structured KnowledgeEvidence into a ToolMessage artifact reference."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from agent_composition.domain.ports import ToolResult, thaw_value
from core.observability.logger import get_logger
from schemas.knowledge_evidence import KnowledgeEvidence
from service.knowledge_evidence.recorder import KnowledgeEvidenceRecorder
from service.knowledge_evidence.references import EVIDENCE_ARTIFACT_KEY

logger = get_logger(__name__)


class KnowledgeEvidenceArtifactPolicy:
    """``ToolArtifactPolicy`` for any tool whose structured output is KnowledgeEvidence.

    The payload is persisted and only its id enters the ToolMessage artifact, so
    the checkpoint (which rewrites every message on every step) stays small.
    """

    def __init__(self, recorder: KnowledgeEvidenceRecorder) -> None:
        self._recorder = recorder

    async def artifact_for(self, tool_name: str, result: ToolResult) -> Mapping[str, Any] | None:
        if result.structured is None:
            return None
        try:
            evidence = KnowledgeEvidence.model_validate(thaw_value(result.structured))
        except ValidationError:
            logger.debug("Structured output of tool '%s' is not knowledge evidence", tool_name)
            return None
        evidence_id = await self._recorder.record(evidence)
        return {EVIDENCE_ARTIFACT_KEY: str(evidence_id)} if evidence_id else None
