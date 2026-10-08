"""KnowledgeEvidenceArtifactPolicy: structured tool output -> ToolMessage artifact reference."""

from __future__ import annotations

import pytest

from agent_composition.domain.ports import ToolResult
from service.knowledge_evidence.artifact_policy import KnowledgeEvidenceArtifactPolicy
from service.knowledge_evidence.recorder import KnowledgeEvidenceRecorder
from service.knowledge_evidence.references import EVIDENCE_ARTIFACT_KEY

from .conftest import THREAD_ID, make_evidence


def _policy(store) -> KnowledgeEvidenceArtifactPolicy:
    return KnowledgeEvidenceArtifactPolicy(KnowledgeEvidenceRecorder(store, thread_id_provider=lambda: THREAD_ID))


@pytest.mark.asyncio
async def test_valid_evidence_is_recorded_and_referenced(store) -> None:
    result = ToolResult(output="text", structured=make_evidence().model_dump(mode="json"))

    artifact = await _policy(store).artifact_for("database_search", result)

    (evidence_id,) = store.rows
    assert artifact == {EVIDENCE_ARTIFACT_KEY: str(evidence_id)}
    assert store.rows[evidence_id][1] == make_evidence()


@pytest.mark.asyncio
async def test_tool_without_structured_output_gets_no_artifact(store) -> None:
    assert await _policy(store).artifact_for("calculator", ToolResult(output="4")) is None
    assert store.rows == {}


@pytest.mark.asyncio
async def test_structured_output_that_is_not_evidence_gets_no_artifact(store) -> None:
    result = ToolResult(output="x", structured={"rows": [1, 2, 3]})

    assert await _policy(store).artifact_for("sql_query", result) is None
    assert store.rows == {}


@pytest.mark.asyncio
async def test_unrecorded_evidence_gets_no_artifact(store) -> None:
    store.fail_with = RuntimeError("database is down")
    result = ToolResult(output="text", structured=make_evidence().model_dump(mode="json"))

    assert await _policy(store).artifact_for("database_search", result) is None
