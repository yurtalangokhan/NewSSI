"""HTTP bodies of the retrieval route and their mapping from domain values."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.retrieval.contract import DEFAULT_LIMIT, MAX_LIMIT, RetrievalKind

if TYPE_CHECKING:
    from src.retrieval.contract import (
        RetrievalGraph,
        RetrievalHit,
        RetrievalResult,
    )


class RetrievalRequestBody(BaseModel):
    """HTTP body for the agent-facing retrieval contract."""

    model_config = ConfigDict(extra="forbid")

    query: str
    collection_id: str
    kind: Literal["vector", "graph", "hybrid"] = RetrievalKind.VECTOR.value
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)


class RetrievalHitBody(BaseModel):
    """One retrieval hit in the HTTP response."""

    id: str | None
    content: str
    score: float
    source: str
    metadata: dict[str, object]

    @classmethod
    def from_hit(cls, hit: RetrievalHit) -> RetrievalHitBody:
        """Map a domain hit."""
        return cls(
            id=hit.identifier,
            content=hit.content,
            score=hit.score,
            source=hit.source,
            metadata=dict(hit.metadata),
        )


class RetrievalGraphNodeBody(BaseModel):
    """One entity of the retrieved subgraph."""

    id: str
    name: str
    label: str
    matched: bool
    score: float | None
    properties: dict[str, object]


class RetrievalGraphEdgeBody(BaseModel):
    """One relationship of the retrieved subgraph."""

    id: str | None
    source: str
    target: str
    type: str
    properties: dict[str, object]


class RetrievalGraphBody(BaseModel):
    """The closed subgraph a graph retrieval returned."""

    nodes: list[RetrievalGraphNodeBody]
    edges: list[RetrievalGraphEdgeBody]

    @classmethod
    def from_graph(cls, graph: RetrievalGraph) -> RetrievalGraphBody:
        """Map a domain subgraph."""
        return cls(
            nodes=[
                RetrievalGraphNodeBody(
                    id=node.identifier,
                    name=node.name,
                    label=node.label,
                    matched=node.matched,
                    score=node.score,
                    properties=dict(node.properties),
                )
                for node in graph.nodes
            ],
            edges=[
                RetrievalGraphEdgeBody(
                    id=edge.identifier,
                    source=edge.source,
                    target=edge.target,
                    type=edge.type,
                    properties=dict(edge.properties),
                )
                for edge in graph.edges
            ],
        )


class RetrievalResponseBody(BaseModel):
    """HTTP response for the agent-facing retrieval contract."""

    kind: str
    collection_id: str
    collection_name: str | None = None
    hits: list[RetrievalHitBody]
    context: str
    graph: RetrievalGraphBody | None = None

    @classmethod
    def from_result(cls, result: RetrievalResult) -> RetrievalResponseBody:
        """Map a domain result."""
        return cls(
            kind=result.kind.value,
            collection_id=result.collection_id,
            collection_name=result.collection_name,
            hits=[RetrievalHitBody.from_hit(hit) for hit in result.hits],
            context=result.context,
            graph=RetrievalGraphBody.from_graph(result.graph) if result.graph is not None else None,
        )
