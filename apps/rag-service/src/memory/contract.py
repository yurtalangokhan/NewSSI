"""User long-term-memory semantic search contract.

A Milvus-backed embedding index for "user fact" strings extracted from
chat (long-term memory, owned by agent-service). This is a distinct
concern from document/graph retrieval (src.retrieval): facts are
short, per-user strings with no user-created "collection" concept, so they
share one fixed Milvus collection with user_id-based metadata filtering
rather than the per-collection model documents/graph use.

user-service owns canonical fact storage (Postgres) and calls the write
ports here to keep this index in sync on every create/update/delete.
agent-service calls the search port during chat turns to recall
semantically relevant facts for the current message. Both call through
this contract's HTTP adapter (memory.router); neither talks to Milvus
directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from error_contract import RequiredFieldError, TrustedIdentityRequiredError

from src.memory.bm25 import BM25Okapi
from src.memory.fusion import (
    DEFAULT_LEXICAL_WEIGHT,
    DEFAULT_VECTOR_FLOOR,
    DEFAULT_VECTOR_WEIGHT,
    fuse_hybrid_scores,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable

DEFAULT_SEARCH_LIMIT = 5
MAX_SEARCH_LIMIT = 20


@dataclass(frozen=True)
class TrustedMemoryContext:
    """Identity values from authenticated transport, never from the body."""

    user_id: str


@dataclass(frozen=True)
class MemoryFactHit:
    """One matched fact with fused score and optional source signals."""

    fact_id: str
    content: str
    score: float
    vector_score: float | None = None
    bm25_score: float | None = None


class UpsertFactPort(Protocol):
    """Port for embedding and storing one fact."""

    def __call__(self, *, user_id: str, fact_id: str, content: str) -> Awaitable[None]:
        """Embed content and upsert it into the user's memory index."""


class DeleteFactPort(Protocol):
    """Port for removing one fact's embedding."""

    def __call__(self, *, user_id: str, fact_id: str) -> Awaitable[None]:
        """Remove the embedding for one fact."""


class DeleteAllFactsPort(Protocol):
    """Port for clearing a user's entire memory index."""

    def __call__(self, *, user_id: str) -> Awaitable[None]:
        """Remove every embedding stored for the user."""


class SearchFactsPort(Protocol):
    """Port for semantic search over a user's memory index."""

    def __call__(self, *, user_id: str, query: str, limit: int) -> Awaitable[tuple[MemoryFactHit, ...]]:
        """Return up to `limit` facts most similar to `query`, any score."""


def bound_limit(limit: int) -> int:
    """Clamp a caller limit into the contract range."""
    if limit < 1:
        return 1
    if limit > MAX_SEARCH_LIMIT:
        return MAX_SEARCH_LIMIT
    return limit


class MemoryIndexService:
    """Authorize and execute fact-embedding writes/search through injected ports."""

    def __init__(
        self,
        *,
        upsert: UpsertFactPort,
        delete: DeleteFactPort,
        delete_all: DeleteAllFactsPort,
        search: SearchFactsPort,
    ) -> None:
        """Store injected write/search ports."""
        self._upsert = upsert
        self._delete = delete
        self._delete_all = delete_all
        self._search = search

    async def upsert_fact(self, context: TrustedMemoryContext, *, fact_id: str, content: str) -> None:
        """Embed and index one fact for the trusted user."""
        user_id = _require_user(context)
        fact_id = fact_id.strip()
        content = content.strip()
        if not fact_id:
            raise RequiredFieldError("fact_id")
        if not content:
            raise RequiredFieldError("content")
        await self._upsert(user_id=user_id, fact_id=fact_id, content=content)

    async def delete_fact(self, context: TrustedMemoryContext, *, fact_id: str) -> None:
        """Remove one fact's embedding for the trusted user."""
        user_id = _require_user(context)
        fact_id = fact_id.strip()
        if not fact_id:
            raise RequiredFieldError("fact_id")
        await self._delete(user_id=user_id, fact_id=fact_id)

    async def delete_all_facts(self, context: TrustedMemoryContext) -> None:
        """Remove every embedding stored for the trusted user."""
        user_id = _require_user(context)
        await self._delete_all(user_id=user_id)

    async def search_facts(
        self,
        context: TrustedMemoryContext,
        *,
        query: str,
        limit: int = DEFAULT_SEARCH_LIMIT,
        vector_floor: float = DEFAULT_VECTOR_FLOOR,
        vector_weight: float = DEFAULT_VECTOR_WEIGHT,
        lexical_weight: float = DEFAULT_LEXICAL_WEIGHT,
    ) -> tuple[MemoryFactHit, ...]:
        """Return facts relevant to `query` for the trusted user.

        Fuses Milvus's dense ranking with Turkish-aware BM25Okapi lexical
        ranking via weighted RRF, the same scheme graph.service.hybrid_search
        uses. An empty query returns no results without calling the port.
        """
        user_id = _require_user(context)
        query = query.strip()
        if not query:
            return ()
        bounded = bound_limit(limit)
        hits = await self._search(user_id=user_id, query=query, limit=bounded)
        if not hits:
            return ()

        # Lexical ranking over the same candidates. Raw scores, not
        # max-normalised ones: RRF reads their order, and normalising made
        # the top candidate 1.0 whenever any overlap existed at all.
        bm25 = BM25Okapi.from_documents([h.content for h in hits])
        bm25_scores = bm25.score_all(query)

        fused = fuse_hybrid_scores(
            hits,
            bm25_scores,
            vector_weight=vector_weight,
            lexical_weight=lexical_weight,
            vector_floor=vector_floor,
        )
        return fused[:bounded]


def _require_user(context: TrustedMemoryContext) -> str:
    if not context or not context.user_id:
        raise TrustedIdentityRequiredError()
    return context.user_id
