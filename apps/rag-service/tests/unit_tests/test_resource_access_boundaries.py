"""Use cases must authorize resources before reading graph or document data.

The routes are transport adapters that turn a typed failure into the response
envelope, so the authorization boundary is asserted where it is enforced: the
framework-free ``api_service`` modules, which raise the typed error.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import httpx
import pytest
from error_contract import ForbiddenError, NotFoundError

from src.documents import api_service as documents
from src.documents.service import Collection
from src.graph import api_service as graph
from src.graph.schemas import CypherQueryRequest
from src.shared.authorization import AuthorizationClient


async def test_raw_cypher_requires_system_admin_before_graph_io(monkeypatch):
    monkeypatch.setattr(Collection, "ensure_exists", AsyncMock())
    monkeypatch.setattr(
        AuthorizationClient, "is_admin", AsyncMock(return_value=False), raising=False
    )
    store = MagicMock()
    monkeypatch.setattr(graph, "GraphStore", store)
    with pytest.raises(ForbiddenError):
        await graph.execute_cypher(
            CypherQueryRequest(collection_id="shared", query="MATCH (n) RETURN n"),
            "member",
            "token",
        )
    store.assert_not_called()


@pytest.mark.parametrize(
    ("response", "expected"),
    [(True, True), (False, False), ("true", False), (None, False)],
)
async def test_admin_check_uses_authoritative_boolean(monkeypatch, response, expected):
    client = AsyncMock()
    client.get.return_value = httpx.Response(
        200,
        json={
            "statusCode": 200,
            "message": None,
            "data": {"is_admin": response},
            "error": None,
        },
        request=httpx.Request("GET", "http://user-service/permissions"),
    )
    # The call borrows the shared per-peer client instead of opening one of
    # its own, so the double replaces get_shared_client, not httpx.AsyncClient.
    monkeypatch.setattr(
        "src.shared.authorization.get_shared_client", lambda *a, **kw: client
    )
    assert await AuthorizationClient().is_admin("member") is expected


async def test_connector_document_list_uses_authenticated_identity(monkeypatch):
    collection = MagicMock(list=AsyncMock(return_value=[]))
    factory = MagicMock(return_value=collection)
    monkeypatch.setattr(documents, "Collection", factory)
    manager = MagicMock(
        get=AsyncMock(return_value={"metadata": {"connector_type": "postgres"}})
    )
    monkeypatch.setattr(
        "src.collections.service.CollectionsManager", lambda *a: manager
    )
    await documents.documents_list(UUID(int=1), "member", 10, 0)
    assert factory.call_args.kwargs["user_id"] == "member"


@pytest.mark.parametrize(
    ("endpoint", "extra"),
    [
        ("list_nodes", {"limit": 10, "offset": 0, "label": None}),
        ("list_edges", {"limit": 10, "offset": 0}),
        ("get_graph_data", {"node_limit": 10, "edge_limit": 10}),
        ("get_build_status", {}),
        ("pause_build", {}),
        ("resume_build", {}),
        ("stop_build", {}),
        ("delete_graph", {}),
    ],
)
async def test_graph_rejects_ungranted_collection_before_io(monkeypatch, endpoint, extra):
    deny = AsyncMock(side_effect=NotFoundError(message="Not found"))
    monkeypatch.setattr(Collection, "ensure_exists", deny)
    store = MagicMock()
    monkeypatch.setattr(graph, "GraphStore", store)
    with pytest.raises(NotFoundError):
        await getattr(graph, endpoint)(
            collection_id="private", user_id="member", **extra
        )
    store.assert_not_called()


async def test_graph_listing_intersects_visible_collections(monkeypatch):
    monkeypatch.setattr(
        graph.GraphStore,
        "list_graph_collection_ids",
        AsyncMock(return_value=["shared", "private"]),
    )
    monkeypatch.setattr(
        "src.collections.service.CollectionsManager.list",
        AsyncMock(return_value=[{"uuid": "shared"}]),
    )
    assert await graph.list_graph_collections("member") == ["shared"]
