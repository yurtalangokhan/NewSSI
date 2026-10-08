"""``RetrievalGateway`` backed by rag-service and the request's access token."""

from __future__ import annotations

from typing import Any

from integrations import rag_client
from integrations.rag_client import RagChunk
from integrations.user_service_client import get_current_access_token


class RagRetrievalGateway:
    """Delegates to ``integrations.rag_client``, which owns the wire contract."""

    def access_token(self) -> str | None:
        return get_current_access_token()

    async def search_documents(
        self, collection_id: str, query: str, *, top_k: int, threshold: float | None, access_token: str | None
    ) -> list[RagChunk]:
        return await rag_client.search_documents(
            collection_id, query, top_k=top_k, threshold=threshold, access_token=access_token
        )

    async def search_graph(self, collection_id: str, query: str, *, limit: int, access_token: str | None) -> Any:
        return await rag_client.search_graph(collection_id, query, limit=limit, access_token=access_token)

    async def search_graph_entities(
        self, collection_id: str, query: str, *, entity_type: str | None, limit: int, access_token: str | None
    ) -> Any:
        return await rag_client.search_graph_entities(
            collection_id, query, entity_type=entity_type, limit=limit, access_token=access_token
        )

    async def graph_neighborhood(
        self, collection_id: str, entity_id: str, *, depth: int, limit: int, access_token: str | None
    ) -> Any:
        return await rag_client.graph_neighborhood(
            collection_id, entity_id, depth=depth, limit=limit, access_token=access_token
        )

    async def graph_stats(self, collection_id: str, *, access_token: str | None) -> Any:
        return await rag_client.graph_stats(collection_id, access_token=access_token)
