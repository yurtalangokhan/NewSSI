"""What the flow retrieval nodes need from the outside world.

Declared here so ``agents`` depends on an abstraction; ``service.flow_retrieval``
supplies the rag-service-backed implementation.
"""

from __future__ import annotations

from typing import Any, Protocol


class RetrievedChunk(Protocol):
    """A retrieved document chunk as the flow nodes consume it."""

    text: str

    def as_dict(self) -> dict[str, Any]: ...


class RetrievalGateway(Protocol):
    """Knowledge retrieval for flow nodes, authorised as the calling user."""

    def access_token(self) -> str | None: ...

    async def search_documents(
        self, collection_id: str, query: str, *, top_k: int, threshold: float | None, access_token: str | None
    ) -> list[Any]: ...

    async def search_graph(self, collection_id: str, query: str, *, limit: int, access_token: str | None) -> Any: ...

    async def search_graph_entities(
        self, collection_id: str, query: str, *, entity_type: str | None, limit: int, access_token: str | None
    ) -> Any: ...

    async def graph_neighborhood(
        self, collection_id: str, entity_id: str, *, depth: int, limit: int, access_token: str | None
    ) -> Any: ...

    async def graph_stats(self, collection_id: str, *, access_token: str | None) -> Any: ...
