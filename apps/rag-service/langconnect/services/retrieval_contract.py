"""Agent-facing retrieval contract for tools-service knowledge tools.

This module is additive. Existing collection and graph search routes are
unchanged. Callers inject vector/graph/authorization ports so Milvus, Neo4j,
and embedding clients stay behind RAG-service adapters.
"""

from __future__ import annotations

from collections.abc import Awaitable, Mapping
from dataclasses import dataclass, field
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
class RetrievalResult:
    """Structured retrieval output with redacted metadata."""

    kind: RetrievalKind
    collection_id: str
    hits: tuple[RetrievalHit, ...]
    context: str


@dataclass(frozen=True)
class VectorDocument:
    """Vector-store hit after adapter mapping."""

    identifier: str | None
    content: str
    score: float
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphDocument:
    """Graph-store hit after adapter mapping."""

    identifier: str | None
    content: str
    score: float
    context: str = ""
    metadata: Mapping[str, object] = field(default_factory=dict)


class VectorSearchPort(Protocol):
    """Port for collection vector search."""

    def __call__(
        self, query: str, *, limit: int
    ) -> Awaitable[tuple[VectorDocument, ...]]:
        """Search the vector store for the authorized collection."""


class GraphSearchPort(Protocol):
    """Port for collection graph search."""

    def __call__(
        self, query: str, *, limit: int
    ) -> Awaitable[tuple[GraphDocument, ...]]:
        """Search the graph store for the authorized collection."""


class CollectionAuthorizePort(Protocol):
    """Port for user/tenant collection read authorization."""

    def __call__(self, user_id: str, collection_id: str) -> Awaitable[bool]:
        """Return True when the user may read the collection."""


def assert_model_arguments_trusted_free(model_arguments: Mapping[str, object]) -> None:
    """Reject reserved trusted fields smuggled through query arguments."""

    def _scan(value: object) -> str | None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if isinstance(key, str) and (
                    key.lower() in RESERVED_QUERY_KEYS
                    or key.lower().startswith("x-binding-ref-")
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
    """Authorize and execute vector/graph retrieval through injected ports."""

    def __init__(
        self,
        *,
        vector_search: VectorSearchPort,
        graph_search: GraphSearchPort,
        authorize: CollectionAuthorizePort,
    ) -> None:
        """Store injected search and authorization ports."""
        self._vector_search = vector_search
        self._graph_search = graph_search
        self._authorize = authorize

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        """Run authorized retrieval and return bounded, redacted hits."""
        assert_model_arguments_trusted_free(request.model_arguments)
        query = request.query.strip()
        collection_id = request.collection_id.strip()
        if not query:
            raise ValidationFailedError(message="Retrieval query must not be empty.")
        if not collection_id:
            raise ValidationFailedError(
                message="Collection reference must not be empty."
            )
        user_id = request.trusted_context.user_id if request.trusted_context else None
        if not user_id:
            raise ForbiddenError(
                message="Trusted user identity is required for retrieval."
            )
        allowed = await self._authorize(user_id, collection_id)
        if not allowed:
            raise ForbiddenError(
                message="Access denied to the requested collection.",
                details={"collection_id": collection_id},
            )

        limit = bound_limit(request.limit)
        hits: list[RetrievalHit] = []
        context = ""

        if request.kind in {RetrievalKind.VECTOR, RetrievalKind.HYBRID}:
            vector_hits = _hits_from_vector(
                await self._vector_search(query, limit=limit),
            )
            hits.extend(vector_hits)
        if request.kind in {RetrievalKind.GRAPH, RetrievalKind.HYBRID}:
            graph_docs = await self._graph_search(query, limit=limit)
            graph_hits = _hits_from_graph(graph_docs)
            if request.kind is RetrievalKind.HYBRID:
                hits = _interleave_sources(hits, graph_hits, limit)
            else:
                hits.extend(graph_hits)
            if graph_docs:
                context = graph_docs[0].context

        return RetrievalResult(
            kind=request.kind,
            collection_id=collection_id,
            hits=tuple(hits[:limit]),
            context=context,
        )


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


def _hits_from_graph(documents: tuple[GraphDocument, ...]) -> list[RetrievalHit]:
    return [
        RetrievalHit(
            identifier=document.identifier,
            content=document.content,
            score=document.score,
            source=RetrievalKind.GRAPH.value,
            metadata=redact_mapping(document.metadata),
        )
        for document in documents
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
