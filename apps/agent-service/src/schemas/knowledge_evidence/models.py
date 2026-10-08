"""KnowledgeEvidence v1: what one knowledge retrieval call handed the model.

Producers (tools-service knowledge tools, agent-service flow retrieval nodes)
build it; agent-service persists it and streams it to the web client. Models
are immutable and self-bounding, so a consumer can trust any instance it holds.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from .limits import (
    MAX_CHUNK_CHARS,
    MAX_CHUNKS,
    MAX_COLLECTIONS,
    MAX_GRAPH_EDGES,
    MAX_GRAPH_NODES,
    MAX_LABEL_CHARS,
    MAX_MODEL_CONTEXT_CHARS,
    MAX_QUERY_CHARS,
    MAX_SOURCE_FIELD_CHARS,
    SCHEMA_VERSION,
)
from .sanitize import PropertyValue, finite_or_none, sanitize_properties, truncate


class EvidenceKind(StrEnum):
    """What the retrieval returned: document chunks or a graph neighbourhood."""

    DOCUMENT = "document"
    GRAPH = "graph"


class _EvidenceModel(BaseModel):
    # Unknown keys are ignored so an older reader accepts a newer producer.
    model_config = ConfigDict(frozen=True, extra="ignore")


def _bounded_text(value: Any, limit: int) -> Any:
    return truncate(value, limit)[0] if isinstance(value, str) else value


class EvidenceSource(_EvidenceModel):
    """Where a chunk came from. Only these fields ever reach the browser."""

    document: str | None = None
    title: str | None = None
    page: int | None = None
    section: str | None = None
    file_id: str | None = None

    @field_validator("document", "title", "section", "file_id", mode="before")
    @classmethod
    def _bound(cls, value: Any) -> Any:
        return _bounded_text(value, MAX_SOURCE_FIELD_CHARS)

    @classmethod
    def from_metadata(cls, metadata: Mapping[str, Any] | None) -> EvidenceSource:
        """Pick the displayable source fields out of vector-store chunk metadata."""
        metadata = metadata or {}
        return cls(
            document=_non_empty_text(metadata.get("source")),
            title=_non_empty_text(metadata.get("title")),
            page=_page_number(metadata.get("page", metadata.get("page_number"))),
            section=_non_empty_text(metadata.get("section")),
            file_id=_non_empty_text(metadata.get("file_id")),
        )


def _non_empty_text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _page_number(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


class EvidenceCollection(_EvidenceModel):
    """A searched collection, by id and (when known) its display name."""

    id: str
    name: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def _bound(cls, value: Any) -> Any:
        return _bounded_text(value, MAX_LABEL_CHARS)


class EvidenceChunk(_EvidenceModel):
    """One retrieved chunk, ranked by ``ref`` (1-based, as the model saw it)."""

    ref: int = Field(ge=1)
    id: str | None = None
    score: float | None = None
    content: str
    truncated: bool = False
    collection_id: str | None = None
    source: EvidenceSource = Field(default_factory=EvidenceSource)

    @classmethod
    def from_hit(
        cls,
        *,
        ref: int,
        collection_id: str,
        content: str,
        hit_id: str | None = None,
        score: float | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> EvidenceChunk:
        """A chunk from a retrieval hit, its source read out of the hit metadata."""
        return cls(
            ref=ref,
            id=hit_id,
            score=score,
            content=content,
            collection_id=collection_id,
            source=EvidenceSource.from_metadata(metadata),
        )

    @model_validator(mode="before")
    @classmethod
    def _bound_content(cls, data: Any) -> Any:
        if not isinstance(data, dict) or not isinstance(data.get("content"), str):
            return data
        content, cut = truncate(data["content"], MAX_CHUNK_CHARS)
        return {**data, "content": content, "truncated": bool(data.get("truncated")) or cut}

    @field_validator("score", mode="before")
    @classmethod
    def _finite_score(cls, value: Any) -> float | None:
        return finite_or_none(value)


class EvidenceGraphNode(_EvidenceModel):
    """An entity. ``matched`` separates query hits from neighbourhood expansion."""

    id: str
    name: str
    label: str = "Entity"
    matched: bool = False
    score: float | None = None
    properties: dict[str, PropertyValue] = Field(default_factory=dict)

    @field_validator("name", "label", mode="before")
    @classmethod
    def _bound(cls, value: Any) -> Any:
        return _bounded_text(value, MAX_LABEL_CHARS)

    @field_validator("score", mode="before")
    @classmethod
    def _finite_score(cls, value: Any) -> float | None:
        return finite_or_none(value)

    @field_validator("properties", mode="before")
    @classmethod
    def _sanitize(cls, value: Any) -> dict[str, PropertyValue]:
        return sanitize_properties(value)


class EvidenceGraphEdge(_EvidenceModel):
    """A directed relationship between two nodes of the same evidence graph."""

    id: str | None = None
    source: str
    target: str
    type: str
    properties: dict[str, PropertyValue] = Field(default_factory=dict)

    @field_validator("type", mode="before")
    @classmethod
    def _bound(cls, value: Any) -> Any:
        return _bounded_text(value, MAX_LABEL_CHARS)

    @field_validator("properties", mode="before")
    @classmethod
    def _sanitize(cls, value: Any) -> dict[str, PropertyValue]:
        return sanitize_properties(value)


class EvidenceGraph(_EvidenceModel):
    """A self-contained subgraph: every edge endpoint is one of ``nodes``."""

    # Field order matters: ``edges`` is validated against the kept ``nodes``.
    nodes: tuple[EvidenceGraphNode, ...] = ()
    edges: tuple[EvidenceGraphEdge, ...] = ()

    @field_validator("nodes", mode="after")
    @classmethod
    def _cap_nodes(cls, nodes: tuple[EvidenceGraphNode, ...]) -> tuple[EvidenceGraphNode, ...]:
        return nodes[:MAX_GRAPH_NODES]

    @field_validator("edges", mode="after")
    @classmethod
    def _close_edges(cls, edges: tuple[EvidenceGraphEdge, ...], info: ValidationInfo) -> tuple[EvidenceGraphEdge, ...]:
        node_ids = {node.id for node in info.data.get("nodes", ())}
        closed = (edge for edge in edges if edge.source in node_ids and edge.target in node_ids)
        return tuple(closed)[:MAX_GRAPH_EDGES]


class KnowledgeEvidence(_EvidenceModel):
    """The evidence one retrieval call produced, bounded for storage and display."""

    schema_version: Literal[1] = SCHEMA_VERSION
    kind: EvidenceKind
    tool: str
    query: str
    collections: tuple[EvidenceCollection, ...] = ()
    chunks: tuple[EvidenceChunk, ...] = ()
    graph: EvidenceGraph | None = None
    model_context: str = ""
    model_context_truncated: bool = False
    elapsed_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="before")
    @classmethod
    def _bound_model_context(cls, data: Any) -> Any:
        if not isinstance(data, dict) or not isinstance(data.get("model_context"), str):
            return data
        context, cut = truncate(data["model_context"], MAX_MODEL_CONTEXT_CHARS)
        return {
            **data,
            "model_context": context,
            "model_context_truncated": bool(data.get("model_context_truncated")) or cut,
        }

    @field_validator("query", mode="before")
    @classmethod
    def _bound_query(cls, value: Any) -> Any:
        return _bounded_text(value, MAX_QUERY_CHARS)

    @field_validator("collections", mode="before")
    @classmethod
    def _cap_collections(cls, value: Any) -> Any:
        return value[:MAX_COLLECTIONS] if isinstance(value, list | tuple) else value

    @field_validator("chunks", mode="before")
    @classmethod
    def _cap_chunks(cls, value: Any) -> Any:
        return value[:MAX_CHUNKS] if isinstance(value, list | tuple) else value
