"""Agent-facing retrieval contract for tools-service knowledge tools.

This module is additive. Existing collection and graph search routes are
unchanged. Callers inject vector/graph/authorization ports so Milvus, Neo4j,
and embedding clients stay behind RAG-service adapters.
"""

from __future__ import annotations

from collections.abc import Awaitable, Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Protocol

from error_contract import ForbiddenError, ValidationFailedError

DEFAULT_LIMIT = 10
MAX_LIMIT = 50

RESERVED_QUERY_KEYS = frozenset(
    {
        "trusted_context",
        "trusted_context_ref",
        "user_id",
        "tenant_id",
        "binding_references",
        "attachment_handles",
        "project_id",
        "request_id",
        "x-internal-token",
        "x-user-id",
        "x-tenant-id",
        "x-binding-ref",
    }
)

_REDACTED_FIELDS = frozenset(
    {
        "token",
        "access_token",
        "secret",
        "password",
        "api_key",
        "binding_references",
        "trusted_context",
        "x-internal-token",
    }
)


class RetrievalKind(StrEnum):
    """Supported retrieval modes for the agent-facing contract."""

    VECTOR = "vector"
    GRAPH = "graph"
    HYBRID = "hybrid"


@dataclass(frozen=True)
class TrustedRetrievalContext:
    """Identity values from authenticated transport, never from model arguments."""

    user_id: str | None = None
    tenant_id: str | None = None
    request_id: str | None = None


@dataclass(frozen=True)
class RetrievalRequest:
    """Normalized retrieval input using an opaque collection reference."""

    query: str
    collection_id: str
    kind: RetrievalKind = RetrievalKind.VECTOR
    limit: int = DEFAULT_LIMIT
    model_arguments: Mapping[str, object] = field(default_factory=dict)
    trusted_context: TrustedRetrievalContext | None = None


@dataclass(frozen=True)
class RetrievalHit:
    """One bounded retrieval result suitable for a tool payload."""

    identifier: str | None
    content: str
    score: float
    source: str
    metadata: Mapping[str, object]


@dataclass(frozen=True)
class GraphNodeView:
    """One entity of a graph retrieval; ``matched`` marks direct query hits."""

    identifier: str
    name: str
    label: str
    matched: bool
    score: float | None
    properties: Mapping[str, object]


@dataclass(frozen=True)
class GraphEdgeView:
    """One directed relationship between two ``GraphNodeView`` entities."""

    identifier: str | None
    source: str
    target: str
    type: str
    properties: Mapping[str, object]


@dataclass(frozen=True)
class GraphRetrieval:
    """Graph-store answer: a closed subgraph plus the text context for RAG."""

    nodes: tuple[GraphNodeView, ...]
    edges: tuple[GraphEdgeView, ...]
    context: str
    score: float


@dataclass(frozen=True)
class RetrievalGraph:
    """The redacted subgraph a graph retrieval returned."""

    nodes: tuple[GraphNodeView, ...]
    edges: tuple[GraphEdgeView, ...]


@dataclass(frozen=True)
class AuthorizedCollection:
    """A collection the trusted user may read, with its display name."""

    identifier: str
    name: str | None


@dataclass(frozen=True)
class RetrievalResult:
    """Structured retrieval output with redacted metadata."""

    kind: RetrievalKind
    collection_id: str
    hits: tuple[RetrievalHit, ...]
    context: str
    collection_name: str | None = None
    graph: RetrievalGraph | None = None


@dataclass(frozen=True)
class VectorDocument:
    """Vector-store hit after adapter mapping."""

    identifier: str | None
    content: str
    score: float
    metadata: Mapping[str, object] = field(default_factory=dict)


class VectorSearchPort(Protocol):
    """Port for collection vector search."""

    def __call__(self, query: str, *, limit: int) -> Awaitable[tuple[VectorDocument, ...]]:
        """Search the vector store for the authorized collection."""


class GraphSearchPort(Protocol):
    """Port for collection graph search."""

    def __call__(self, query: str, *, limit: int) -> Awaitable[GraphRetrieval]:
        """Search the graph store for the authorized collection."""


class CollectionAuthorizePort(Protocol):
    """Port for user/tenant collection read authorization."""

    def __call__(self, user_id: str, collection_id: str) -> Awaitable[AuthorizedCollection | None]:
        """Return the collection when the user may read it, else ``None``."""


def assert_model_arguments_trusted_free(model_arguments: Mapping[str, object]) -> None:
    """Reject reserved trusted fields smuggled through query arguments."""

    def _scan(value: object) -> str | None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if isinstance(key, str) and (
                    key.lower() in RESERVED_QUERY_KEYS or key.lower().startswith("x-binding-ref-")
                ):
                    return key
                found = _scan(item)
                if found is not None:
                    return found
        if isinstance(value, list | tuple):
            for item in value:
                found = _scan(item)
                if found is not None:
                    return found
        return None

    found_key = _scan(model_arguments)
    if found_key is not None:
        raise ValidationFailedError(
            code="forbidden_trusted_field",
            message=f"Model-visible argument '{found_key}' carries a trusted field.",
            details={"key": found_key},
        )


def redact_mapping(value: Mapping[str, object]) -> dict[str, object]:
    """Return a copy with secret-like fields masked."""
    redacted: dict[str, object] = {}
    for key, item in value.items():
        if isinstance(key, str) and key.lower() in _REDACTED_FIELDS:
            redacted[key] = "***REDACTED***"
        elif isinstance(item, Mapping):
            redacted[key] = redact_mapping(item)
        else:
            redacted[key] = item
    return redacted


def bound_limit(limit: int) -> int:
    """Clamp a caller limit into the contract range."""
    if limit < 1:
        return 1
    if limit > MAX_LIMIT:
        return MAX_LIMIT
    return limit


class RetrievalService:
    """Authorize and execute vector/graph retrieval through injected ports.

    The vector and graph ports are already bound to one collection.
    ``retrieve`` authorizes through the ``authorize`` port;
    ``retrieve_authorized`` is the explicit entry for callers that have already
    established read access to the collection and so need no authorize port.
    """

    def __init__(
        self,
        *,
        vector_search: VectorSearchPort,
        graph_search: GraphSearchPort,
        authorize: CollectionAuthorizePort | None = None,
    ) -> None:
        """Store injected search ports and the optional authorization port."""
        self._vector_search = vector_search
        self._graph_search = graph_search
        self._authorize = authorize

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        """Authorize the caller, then return bounded, redacted retrieval."""
        if self._authorize is None:
            raise RuntimeError(
                "RetrievalService.retrieve needs an authorize port; "
                "use retrieve_authorized for an already-vetted collection."
            )
        query, collection_id, user_id = _validated(request)
        collection = await self._authorize(user_id, collection_id)
        if collection is None:
            raise ForbiddenError(
                message="Access denied to the requested collection.",
                details={"collection_id": collection_id},
            )
        return await self._execute(request, query, collection_id, collection)

    async def retrieve_authorized(self, request: RetrievalRequest, collection: AuthorizedCollection) -> RetrievalResult:
        """Retrieve from a collection the caller already vetted for this user."""
        query, collection_id, _ = _validated(request)
        if collection.identifier != collection_id:
            raise ForbiddenError(
                message="Access denied to the requested collection.",
                details={"collection_id": collection_id},
            )
        return await self._execute(request, query, collection_id, collection)

    async def _execute(
        self,
        request: RetrievalRequest,
        query: str,
        collection_id: str,
        collection: AuthorizedCollection,
    ) -> RetrievalResult:
        limit = bound_limit(request.limit)
        vector_hits: list[RetrievalHit] = []
        graph_hits: list[RetrievalHit] = []
        contexts: list[str] = []
        graph: RetrievalGraph | None = None

        if request.kind in {RetrievalKind.GRAPH, RetrievalKind.HYBRID}:
            graph_retrieval = await self._graph_search(query, limit=limit)
            graph = redact_graph(graph_retrieval)
            graph_hits = _hits_from_graph(graph, graph_retrieval.score)
            contexts.append(graph_retrieval.context)
        if request.kind in {RetrievalKind.VECTOR, RetrievalKind.HYBRID}:
            vector_hits = _hits_from_vector(
                await self._vector_search(query, limit=limit),
            )
            contexts.append(format_vector_context(vector_hits))

        hits = (
            _interleave_sources(vector_hits, graph_hits, limit)
            if request.kind is RetrievalKind.HYBRID
            else [*vector_hits, *graph_hits]
        )
        return RetrievalResult(
            kind=request.kind,
            collection_id=collection_id,
            hits=tuple(hits[:limit]),
            context="\n\n".join(context for context in contexts if context),
            collection_name=collection.name,
            graph=graph,
        )


def _validated(request: RetrievalRequest) -> tuple[str, str, str]:
    """Return the stripped query, collection id and trusted user id."""
    assert_model_arguments_trusted_free(request.model_arguments)
    query = request.query.strip()
    collection_id = request.collection_id.strip()
    if not query:
        raise ValidationFailedError(message="Retrieval query must not be empty.")
    if not collection_id:
        raise ValidationFailedError(message="Collection reference must not be empty.")
    user_id = request.trusted_context.user_id if request.trusted_context else None
    if not user_id:
        raise ForbiddenError(message="Trusted user identity is required for retrieval.")
    return query, collection_id, user_id


def format_vector_context(hits: list[RetrievalHit]) -> str:
    """Number vector hits the way an LLM can cite them: ``[n] (source)``."""
    blocks: list[str] = []
    for position, hit in enumerate(hits, start=1):
        source = hit.metadata.get("source") or hit.metadata.get("title")
        header = f"[{position}] ({source})" if source else f"[{position}]"
        blocks.append(f"{header}\n{hit.content}")
    return "\n\n".join(blocks)


def _hits_from_vector(documents: tuple[VectorDocument, ...]) -> list[RetrievalHit]:
    return [
        RetrievalHit(
            identifier=document.identifier,
            content=document.content,
            score=document.score,
            source=RetrievalKind.VECTOR.value,
            metadata=redact_mapping(document.metadata),
        )
        for document in documents
    ]


def redact_graph(graph: RetrievalGraph | GraphRetrieval) -> RetrievalGraph:
    """Return the subgraph with secret-like node and edge properties masked."""
    return RetrievalGraph(
        nodes=tuple(replace(node, properties=redact_mapping(node.properties)) for node in graph.nodes),
        edges=tuple(replace(edge, properties=redact_mapping(edge.properties)) for edge in graph.edges),
    )


def _hits_from_graph(graph: RetrievalGraph, score: float) -> list[RetrievalHit]:
    return [
        RetrievalHit(
            identifier=node.identifier,
            content=node.name,
            score=node.score if node.score is not None else score,
            source=RetrievalKind.GRAPH.value,
            metadata={"label": node.label, "properties": node.properties},
        )
        for node in graph.nodes
    ]


def _interleave_sources(
    vector_hits: list[RetrievalHit], graph_hits: list[RetrievalHit], limit: int
) -> list[RetrievalHit]:
    mixed: list[RetrievalHit] = []
    max_len = max(len(vector_hits), len(graph_hits))
    for index in range(max_len):
        if index < len(vector_hits):
            mixed.append(vector_hits[index])
        if index < len(graph_hits):
            mixed.append(graph_hits[index])
        if len(mixed) >= limit:
            break
    return mixed
