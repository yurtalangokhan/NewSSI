from unittest.mock import AsyncMock, patch

import pytest

from integrations.rag_retrieval_gateway import RagRetrievalGateway

_CLIENT = "integrations.rag_retrieval_gateway.rag_client"


@pytest.mark.asyncio
async def test_document_search_forwards_arguments_and_token():
    with patch(f"{_CLIENT}.search_documents", AsyncMock(return_value=["chunk"])) as search:
        result = await RagRetrievalGateway().search_documents(
            "col", "q", top_k=3, threshold=0.5, access_token="tok"
        )
    assert result == ["chunk"]
    search.assert_awaited_once_with("col", "q", top_k=3, threshold=0.5, access_token="tok")


@pytest.mark.asyncio
async def test_graph_calls_forward_arguments_and_token():
    gateway = RagRetrievalGateway()
    with patch(f"{_CLIENT}.graph_neighborhood", AsyncMock(return_value={"nodes": []})) as hood:
        await gateway.graph_neighborhood("col", "e1", depth=2, limit=5, access_token="tok")
    hood.assert_awaited_once_with("col", "e1", depth=2, limit=5, access_token="tok")
    with patch(f"{_CLIENT}.graph_stats", AsyncMock(return_value={})) as stats:
        await gateway.graph_stats("col", access_token="tok")
    stats.assert_awaited_once_with("col", access_token="tok")


def test_access_token_reads_the_request_context():
    with patch("integrations.rag_retrieval_gateway.get_current_access_token", return_value="tok"):
        assert RagRetrievalGateway().access_token() == "tok"
