"""How a checkpoint or timeline refers to a persisted evidence row."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

#: ToolMessage.artifact key holding the evidence row id.
EVIDENCE_ARTIFACT_KEY = "knowledge_evidence_id"

#: ``custom_tool_delta.response_type`` of a packet that carries evidence.
KNOWLEDGE_RESPONSE_TYPE = "knowledge_retrieval"


def parse_uuid(value: Any) -> UUID | None:
    """A well-formed UUID, or ``None`` for anything else."""
    if isinstance(value, UUID):
        return value
    if not isinstance(value, str):
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def evidence_id_from_artifact(artifact: Any) -> UUID | None:
    """The evidence id a ToolMessage artifact references, if it references one."""
    if not isinstance(artifact, Mapping):
        return None
    return parse_uuid(artifact.get(EVIDENCE_ARTIFACT_KEY))
