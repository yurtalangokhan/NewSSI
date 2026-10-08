"""Shared errors must remain safe and localized at MCP boundaries."""

import json
import httpx
import pytest
from localization import set_locale

from src.knowledge.retrieval_client import RagRetrievalClient
from src.knowledge.search_service import KnowledgeSearchService
from src.tools import knowledge_tools


async def test_retrieval_error_does_not_expose_transport_details(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("private credential and host")

    def build_service() -> KnowledgeSearchService:
        return KnowledgeSearchService(
            RagRetrievalClient(
                retrieval_url="http://rag/retrieval",
                internal_token="internal-token",
                transport=httpx.MockTransport(handler),
            )
        )

    monkeypatch.setattr(knowledge_tools, "build_knowledge_search_service", build_service)
    set_locale("tr")
    try:
        outcome = await knowledge_tools.database_search_result("query", ["collection"])
    finally:
        set_locale("en")
    result = json.loads(outcome.content[0].text)
    assert result == {
        "success": False,
        "error": "Bilgi erişimi başarısız oldu.",
        "error_category": "retrieval",
    }


def test_sql_error_category_does_not_depend_on_message():
    from error_contract.connectors import ConnectorSqlConfigurationError

    from src.connectors.sql import _required

    with pytest.raises(ConnectorSqlConfigurationError) as caught:
        _required({}, "host")
    assert caught.value.category == "configuration"
