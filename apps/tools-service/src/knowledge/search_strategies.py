"""Per-mode rules for turning rag-service answers into model text and evidence.

Each strategy owns one retrieval mode: what it asks rag-service for, what the
model reads, and which evidence parts the UI gets. Adding a mode means adding
a strategy, not branching inside the search service.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from .evidence import (
    EvidenceChunk,
    EvidenceGraph,
    EvidenceGraphEdge,
    EvidenceGraphNode,
    EvidenceKind,
)
from .retrieval_client import RagHit, RagRetrievalResponse, RetrievalMode

NO_RESULTS_MESSAGE = "No relevant information found in the configured knowledge collections."


@dataclass(frozen=True)
class AssembledResult:
    """What one search produced for the model and for the evidence record."""

    model_text: str
    chunks: tuple[EvidenceChunk, ...] = ()
    graph: EvidenceGraph | None = None


class SearchStrategy(Protocol):
    mode: RetrievalMode
    evidence_kind: EvidenceKind

    def assemble(self, responses: Sequence[RagRetrievalResponse]) -> AssembledResult: ...


class DocumentSearchStrategy:
    """Vector chunks, numbered once across every searched collection."""

    mode: RetrievalMode = "vector"
    evidence_kind = EvidenceKind.DOCUMENT

    def assemble(self, responses: Sequence[RagRetrievalResponse]) -> AssembledResult:
        hits = [(response.collection_id, hit) for response in responses for hit in response.hits if hit.content]
        chunks = tuple(_chunk(ref, collection_id, hit) for ref, (collection_id, hit) in enumerate(hits, start=1))
        return AssembledResult(model_text=format_chunks(chunks), chunks=chunks)


class GraphSearchStrategy:
    """rag-service's graph context for the model, the merged subgraph for the UI."""

    mode: RetrievalMode = "graph"
    evidence_kind = EvidenceKind.GRAPH

    def assemble(self, responses: Sequence[RagRetrievalResponse]) -> AssembledResult:
        contexts = [response.context.strip() for response in responses if response.context.strip()]
        return AssembledResult(
            model_text="\n\n".join(contexts) or NO_RESULTS_MESSAGE,
            graph=_merged_graph(responses),
        )


def format_chunks(chunks: Sequence[EvidenceChunk]) -> str:
    """``[n] (document)`` blocks, so the model can cite what the UI numbers."""
    if not chunks:
        return NO_RESULTS_MESSAGE
    blocks = []
    for chunk in chunks:
        label = chunk.source.document or chunk.source.title
        header = f"[{chunk.ref}] ({label})" if label else f"[{chunk.ref}]"
        blocks.append(f"{header}\n{chunk.content}")
    return "\n\n".join(blocks)


def _chunk(ref: int, collection_id: str, hit: RagHit) -> EvidenceChunk:
    return EvidenceChunk.from_hit(
        ref=ref,
        collection_id=collection_id,
        content=hit.content,
        hit_id=hit.id,
        score=hit.score,
        metadata=hit.metadata,
    )


def _merged_graph(responses: Sequence[RagRetrievalResponse]) -> EvidenceGraph | None:
    graphs = [response.graph for response in responses if response.graph is not None]
    if not graphs:
        return None
    nodes: dict[str, EvidenceGraphNode] = {}
    edges: list[EvidenceGraphEdge] = []
    for graph in graphs:
        for node in graph.nodes:
            nodes.setdefault(node.id, EvidenceGraphNode.model_validate(node.model_dump()))
        edges.extend(EvidenceGraphEdge.model_validate(edge.model_dump()) for edge in graph.edges)
    return EvidenceGraph(nodes=tuple(nodes.values()), edges=tuple(edges))
