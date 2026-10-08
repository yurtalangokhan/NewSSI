"""Ports the search service depends on; adapters bind them to stores."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from src.retrieval.contract import (
        RetrievalGraph,
        RetrievalKind,
        RetrievalResult,
    )
    from src.search.models import SearchableCollection


class CollectionSearchError(Exception):
    """A collection's store failed to answer; the search carries on without it."""


class CollectionCatalog(Protocol):
    """Lists the collections a user may search."""

    async def list_searchable(self, user_id: str) -> tuple[SearchableCollection, ...]:
        """Return readable collections in display order."""
        ...


class CollectionRetriever(Protocol):
    """Runs one retrieval kind against one already-authorized collection."""

    async def retrieve(
        self,
        collection: SearchableCollection,
        *,
        user_id: str,
        query: str,
        kind: RetrievalKind,
        limit: int,
    ) -> RetrievalResult:
        """Return redacted, bounded retrieval output for the collection.

        Raises:
            CollectionSearchError: The collection's store is unavailable.
        """
        ...


class GraphNeighborhood(Protocol):
    """Reads the graph around nodes of a collection the user may read."""

    async def ensure_readable(self, user_id: str, collection_id: str) -> None:
        """Raise a not-found error when the user may not read the collection."""
        ...

    async def expand(self, collection_id: str, node_id: str, *, depth: int, limit: int) -> RetrievalGraph:
        """Return the ego graph of ``node_id`` up to ``depth`` hops."""
        ...
