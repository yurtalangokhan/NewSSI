"""Collection grants must govern discovery, retrieval, and mutation."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from error_contract import DependencyUnavailableError, NotFoundError
from langchain_core.documents import Document

from src.collections import service as collections_manager
from src.datasources import service as datasources
from src.documents import service as milvus_collection
from src.graph import api_service as graph
from src.graph.schemas import GraphSearchQuery, GraphSearchResult
from src.shared.authorization import AuthorizationClient
from src.retrieval import adapters as retrieval_adapters
from src.retrieval.contract import AuthorizedCollection


@pytest.fixture
def access(monkeypatch):
    authorization = MagicMock()
    authorization.get_user_accessible_collections = AsyncMock(return_value=["shared"])
    authorization.check_collection_access = AsyncMock(return_value={"allowed": True})
    monkeypatch.setattr(
        collections_manager,
        "get_authorization_client",
        lambda: authorization,
        raising=False,
    )
    return authorization


@pytest.fixture
def repository(monkeypatch):
    repo = MagicMock()
    repo.list_collections = AsyncMock(return_value=[])
    repo.get_collection = AsyncMock(return_value=None)
    repo.update_collection = AsyncMock()
    repo.delete_collection = AsyncMock(return_value=1)
    monkeypatch.setattr(collections_manager, "CollectionRepository", lambda *a, **kw: repo)
    return repo


async def test_list_includes_permission_granted_ids(access, repository):
    await collections_manager.CollectionsManager("member").list()
    access.get_user_accessible_collections.assert_awaited_once_with("member")
    repository.list_collections.assert_awaited_once_with(accessible_ids=["shared"])


async def test_selector_exposes_granted_documents_and_graphs(
    access, repository, monkeypatch
):
    async def visible(*, accessible_ids):
        return [
            {"uuid": cid, "name": "Shared knowledge", "metadata": {}}
            for cid in accessible_ids
        ]

    repository.list_collections.side_effect = visible
    monkeypatch.setattr(
        datasources.GraphStore,
        "list_graph_collection_ids",
        AsyncMock(return_value=["shared", "private"]),
    )
    result = await datasources.knowledge_selector("member")
    assert [item["id"] for item in result["document_processing"]] == ["shared"]
    assert [item["id"] for item in result["knowledge_graph"]] == ["shared"]
    access.get_user_accessible_collections.return_value = []
    result = await datasources.knowledge_selector("member")
    assert result == {"document_processing": [], "knowledge_graph": []}


async def test_granted_graph_read_reaches_search(access, repository, monkeypatch):
    repository.get_collection.side_effect = [
        None,
        {"uuid": "shared", "metadata": {"owner_id": "other"}},
    ]
    result = GraphSearchResult(
        context="Organization graph context", nodes=[], edges=[], score=1.0
    )
    search = AsyncMock(return_value=result)
    monkeypatch.setattr(
        graph, "GraphRAGService", lambda **kwargs: MagicMock(hybrid_search=search)
    )
    response = await graph.search_graph(
        GraphSearchQuery(collection_id="shared", query="question"), "member"
    )
    assert response.context == "Organization graph context"
    access.check_collection_access.assert_awaited_once_with("member", "shared", "read")


async def test_granted_read_resolves_collection_without_impersonation(
    access, repository
):
    details = {"uuid": "shared", "table_id": "table", "metadata": {"owner_id": "other"}}
    repository.get_collection.side_effect = [None, details]
    collection = milvus_collection.Collection("shared", "member")
    collection._get_store = MagicMock(
        return_value=MagicMock(
            similarity_search_with_score=MagicMock(
                return_value=[
                    (
                        Document(
                            page_content="Granted document",
                            metadata={"file_id": "file"},
                        ),
                        0.9,
                    )
                ]
            )
        )
    )
    result = await collection.search("question")
    assert result[0]["page_content"] == "Granted document"
    access.check_collection_access.assert_awaited_once_with("member", "shared", "read")
    assert repository.get_collection.call_args.kwargs == {"accessible_ids": ["shared"]}


async def test_denied_collection_never_reaches_vector_store(access, repository):
    access.check_collection_access.return_value = {"allowed": False}
    collection = milvus_collection.Collection("private", "member")
    collection._get_store = MagicMock()
    with pytest.raises(NotFoundError):
        await collection.get("guessed-document")
    collection._get_store.assert_not_called()


@pytest.mark.parametrize(
    ("operation", "level"), [("upsert", "write"), ("delete", "write")]
)
async def test_read_grant_cannot_modify_documents(access, repository, operation, level):
    access.check_collection_access.return_value = {"allowed": False}
    collection = milvus_collection.Collection("shared", "member")
    collection._get_store = MagicMock()
    action = (
        collection.upsert([])
        if operation == "upsert"
        else collection.delete(file_id="file")
    )
    with pytest.raises(NotFoundError):
        await action
    access.check_collection_access.assert_awaited_once_with("member", "shared", level)
    collection._get_store.assert_not_called()


async def test_read_grant_cannot_delete_collection(access, repository):
    access.check_collection_access.return_value = {"allowed": False}
    assert await collections_manager.CollectionsManager("member").delete("shared") == 0
    access.check_collection_access.assert_awaited_once_with("member", "shared", "admin")
    repository.delete_collection.assert_not_called()


async def test_owner_reads_without_authorization_client(access, repository):
    repository.get_collection.return_value = {
        "uuid": "own",
        "metadata": {"owner_id": "member"},
    }
    assert await collections_manager.CollectionsManager("member").get("own")
    access.check_collection_access.assert_not_called()


@pytest.mark.parametrize("owner", ["internal-service", None])
async def test_ingestion_visibility_does_not_grant_write(access, repository, owner):
    repository.get_collection.return_value = {
        "uuid": "public",
        "metadata": {"owner_id": owner},
    }
    manager = collections_manager.CollectionsManager("member")
    assert await manager.get("public") is not None
    access.check_collection_access.assert_not_called()
    access.check_collection_access.return_value = {"allowed": False}
    assert await manager.get("public", "write") is None


async def test_granted_writer_can_update_without_changing_identity(access, repository):
    repository.get_collection.side_effect = [
        None,
        {"uuid": "shared", "metadata": {"owner_id": "other"}},
    ]
    repository.update_collection.return_value = {"uuid": "shared"}
    assert await collections_manager.CollectionsManager("member").update(
        "shared", name="Updated"
    ) == {"uuid": "shared"}
    access.check_collection_access.assert_awaited_once_with("member", "shared", "write")
    assert repository.update_collection.call_args.kwargs["accessible_ids"] == ["shared"]


async def test_retrieval_accepts_owner_without_registered_grant(access, repository):
    repository.get_collection.return_value = {
        "uuid": "own",
        "metadata": {"owner_id": "member"},
    }
    access.check_collection_access.return_value = {"allowed": False}
    assert await retrieval_adapters.authorize_collection_read("member", "own") is not None


async def test_accessible_collections_listing_propagates_outage(monkeypatch):
    client = AuthorizationClient()
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as mock_http:
        monkeypatch.setattr(
            "src.shared.authorization.get_shared_client",
            lambda name: mock_http,
        )
        with pytest.raises(DependencyUnavailableError):
            await client.get_user_accessible_collections("member")
    assert requests[0].url.params["required_permission"] == "read"


@pytest.mark.parametrize(
    ("method", "suffix"),
    [
        ("check_collection_access", "/permissions/check"),
        (
            "get_user_accessible_collections",
            "/permissions/users/member/accessible-resources",
        ),
    ],
)
async def test_collection_grant_requests_use_configured_api_prefix(
    monkeypatch, method, suffix
):
    monkeypatch.setattr(
        "src.shared.authorization.USER_SERVICE_API_PREFIX",
        "/api/v7",
        raising=False,
    )
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "statusCode": 200,
                "message": None,
                "data": {"allowed": True, "resources": []},
                "error": None,
            },
        )

    client = AuthorizationClient()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as mock_http:
        monkeypatch.setattr(
            "src.shared.authorization.get_shared_client", lambda name: mock_http
        )
        args = ("member", "collection") if method.startswith("check") else ("member",)
        await getattr(client, method)(*args)
    # The configured prefix is what must reach user-service. The URL also
    # carries the Gateway route prefix the internal user-service address
    # includes, so the assertion is on the suffix rather than the whole path.
    assert requests[0].url.path.endswith(f"/api/v7{suffix}")


async def _search_rows(access, repository, documents):
    repository.get_collection.return_value = {
        "uuid": "own",
        "table_id": "table",
        "metadata": {"owner_id": "member"},
    }
    collection = milvus_collection.Collection("own", "member")
    collection._get_store = MagicMock(
        return_value=MagicMock(
            similarity_search_with_score=MagicMock(
                return_value=[(document, 0.5) for document in documents]
            )
        )
    )
    return await collection.search("question")


async def test_search_identifies_a_hit_by_its_file_and_its_chunk(access, repository):
    (row,) = await _search_rows(
        access,
        repository,
        [Document(id="pk-1", page_content="text", metadata={"file_id": "file-1"})],
    )

    assert row["id"] == "file-1"
    assert row["chunk_id"] == "pk-1"


async def test_search_falls_back_to_the_chunk_id_without_a_file(access, repository):
    (row,) = await _search_rows(
        access, repository, [Document(id="pk-1", page_content="text", metadata={})]
    )

    assert row["id"] == "pk-1"
    assert row["chunk_id"] == "pk-1"


async def test_read_of_a_foreign_private_collection_requires_a_grant(
    access, repository
):
    # The visibility-filtered lookup finds nothing: the row belongs to someone else.
    repository.get_collection.return_value = None
    access.check_collection_access.return_value = {"allowed": False}

    assert await collections_manager.CollectionsManager("member").get("private") is None
    access.check_collection_access.assert_awaited_once_with("member", "private", "read")


async def test_retrieval_rejects_a_foreign_private_collection(access, repository):
    repository.get_collection.return_value = None
    access.check_collection_access.return_value = {"allowed": False}

    assert (
        await retrieval_adapters.authorize_collection_read("member", "private") is None
    )


async def test_read_short_circuit_only_sees_owner_visible_rows(monkeypatch):
    """The ``read`` fast path trusts ``get_collection``; that lookup must filter
    by owner, so a foreign private collection can never take the fast path.
    """
    from contextlib import asynccontextmanager

    from sqlalchemy.dialects import postgresql

    from src.collections.repository import CollectionRepository

    captured = []

    class _Result:
        def scalar_one_or_none(self):
            return None

    class _Session:
        async def execute(self, statement):
            captured.append(statement)
            return _Result()

    @asynccontextmanager
    async def _session(self):
        yield _Session()

    monkeypatch.setattr(CollectionRepository, "_session", _session)

    assert await CollectionRepository("member").get_collection("private") is None

    sql = str(
        captured[0].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    where = sql.split("WHERE", 1)[1]
    assert "owner_id" in where
    assert "'member'" in where
    assert "IS NULL" in where
    assert "'internal-service'" in where
