from __future__ import annotations

from collections.abc import Callable
import json

from fastmcp import FastMCP
import httpx
import pytest

from src.core.schema import MAX_COLLECTION_IDS
from src.core.trusted import TrustedToolContext
from src.core.trusted_context import set_current_trusted_context
from src.knowledge.evidence import EvidenceKind, KnowledgeEvidence
from src.knowledge.retrieval_client import RagRetrievalClient
from src.knowledge.search_service import KnowledgeSearchService
from src.tools import knowledge_tools

RETRIEVAL_URL = "http://rag-service:8080/api/v1/retrieval"


def _vector_response(collection_id: str, name: str, contents: list[str]) -> dict:
    return {
        "kind": "vector",
        "collection_id": collection_id,
        "collection_name": name,
        "context": "ignored: tools-service numbers chunks itself",
        "hits": [
            {
                "id": f"{collection_id}-chunk-{index}",
                "content": content,
                "score": 0.9 - index * 0.1,
                "source": "vector",
                "metadata": {
                    "source": f"{collection_id}-doc.pdf",
                    "title": "Leave Policy",
                    "file_id": "file-1",
                    "page": 7,
                    "token": "***REDACTED***",
                },
            }
            for index, content in enumerate(contents)
        ],
        "graph": None,
    }


def _graph_response(collection_id: str, context: str, node_prefix: str) -> dict:
    return {
        "kind": "graph",
        "collection_id": collection_id,
        "collection_name": f"Graph {collection_id}",
        "context": context,
        "hits": [],
        "graph": {
            "nodes": [
                {
                    "id": f"{node_prefix}-1",
                    "name": "Annual Leave Carry-over",
                    "label": "Process",
                    "matched": True,
                    "score": 0.0098,
                    "properties": {"limit": "10 days"},
                },
                {
                    "id": f"{node_prefix}-2",
                    "name": "Line Manager",
                    "label": "Role",
                    "matched": False,
                    "score": None,
                    "properties": {},
                },
            ],
            "edges": [
                {
                    "id": f"{node_prefix}-e1",
                    "source": f"{node_prefix}-1",
                    "target": f"{node_prefix}-2",
                    "type": "REQUIRES_APPROVAL_FROM",
                    "properties": {},
                }
            ],
        },
    }


@pytest.fixture
def rag(monkeypatch: pytest.MonkeyPatch) -> Callable[..., list[httpx.Request]]:
    """Route knowledge tools to an in-memory rag-service returning ``responses``."""

    def install(*responses: dict | Exception) -> list[httpx.Request]:
        queue = list(responses)
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            response = queue.pop(0)
            if isinstance(response, Exception):
                raise response
            return httpx.Response(
                200, json={"statusCode": 200, "message": "ok", "data": response, "error": None}
            )

        def build_service() -> KnowledgeSearchService:
            client = RagRetrievalClient(
                retrieval_url=RETRIEVAL_URL,
                internal_token="internal-token",
                transport=httpx.MockTransport(handler),
            )
            return KnowledgeSearchService(client)

        monkeypatch.setattr(knowledge_tools, "build_knowledge_search_service", build_service)
        return requests

    return install


@pytest.fixture(autouse=True)
def trusted_user() -> None:
    set_current_trusted_context(TrustedToolContext(user_id="user-1", tenant_id="tenant-1"))
    yield
    set_current_trusted_context(None)


def _text(result) -> str:
    return "".join(block.text for block in result.content)


async def test_database_search_returns_numbered_text_and_document_evidence(rag) -> None:
    requests = rag(_vector_response("col-1", "HR Policies", ["first chunk", "second chunk"]))

    result = await knowledge_tools.database_search_result("leave carry-over", ["col-1"], limit=3)

    assert _text(result) == (
        "[1] (col-1-doc.pdf)\nfirst chunk\n\n[2] (col-1-doc.pdf)\nsecond chunk"
    )
    evidence = KnowledgeEvidence.model_validate(result.structured_content)
    assert evidence.kind is EvidenceKind.DOCUMENT
    assert evidence.tool == "database_search"
    assert evidence.query == "leave carry-over"
    assert [(c.id, c.name) for c in evidence.collections] == [("col-1", "HR Policies")]
    assert [chunk.ref for chunk in evidence.chunks] == [1, 2]
    first = evidence.chunks[0]
    assert first.content == "first chunk"
    assert first.collection_id == "col-1"
    assert first.source.document == "col-1-doc.pdf"
    assert first.source.title == "Leave Policy"
    assert first.source.page == 7
    assert evidence.model_context == _text(result)
    assert evidence.elapsed_ms is not None

    request = requests[0]
    assert str(request.url) == RETRIEVAL_URL
    assert json.loads(request.content) == {
        "query": "leave carry-over",
        "collection_id": "col-1",
        "kind": "vector",
        "limit": 3,
    }
    assert request.headers["x-internal-token"] == "internal-token"
    assert request.headers["x-user-id"] == "user-1"
    assert request.headers["x-tenant-id"] == "tenant-1"


async def test_database_search_numbers_chunks_across_collections(rag) -> None:
    rag(
        _vector_response("col-1", "HR", ["a"]),
        _vector_response("col-2", "Finance", ["b", "c"]),
    )

    result = await knowledge_tools.database_search_result("q", ["col-1", "col-2"])

    evidence = KnowledgeEvidence.model_validate(result.structured_content)
    assert [(chunk.ref, chunk.collection_id) for chunk in evidence.chunks] == [
        (1, "col-1"),
        (2, "col-2"),
        (3, "col-2"),
    ]
    assert "[3] (col-2-doc.pdf)\nc" in _text(result)


async def test_database_search_without_hits_reports_empty_evidence(rag) -> None:
    rag(_vector_response("col-1", "HR", []))

    result = await knowledge_tools.database_search_result("q", ["col-1"])

    assert _text(result) == "No relevant information found in the configured knowledge collections."
    evidence = KnowledgeEvidence.model_validate(result.structured_content)
    assert evidence.chunks == ()


async def test_graph_search_merges_contexts_and_subgraphs(rag) -> None:
    rag(
        _graph_response("g-1", "first graph context", "a"),
        _graph_response("g-2", "second graph context", "b"),
    )

    result = await knowledge_tools.graph_search_result("roadmap", ["g-1", "g-2"])

    assert _text(result) == "first graph context\n\nsecond graph context"
    evidence = KnowledgeEvidence.model_validate(result.structured_content)
    assert evidence.kind is EvidenceKind.GRAPH
    assert evidence.tool == "graph_search"
    assert evidence.graph is not None
    assert [(node.id, node.matched) for node in evidence.graph.nodes] == [
        ("a-1", True),
        ("a-2", False),
        ("b-1", True),
        ("b-2", False),
    ]
    assert [edge.type for edge in evidence.graph.edges] == ["REQUIRES_APPROVAL_FROM"] * 2
    assert evidence.graph.nodes[0].properties == {"limit": "10 days"}


async def test_knowledge_search_requires_collection_ids(rag) -> None:
    requests = rag()

    result = await knowledge_tools.database_search_result("question", [])

    output = json.loads(_text(result))
    assert output["success"] is False
    assert output["error_category"] == "validation"
    assert result.structured_content is None
    assert requests == []


async def test_database_search_uses_trusted_collection_binding(rag) -> None:
    requests = rag(_vector_response("bound-collection", "HR", ["x"]))
    set_current_trusted_context(
        TrustedToolContext(
            user_id="user-1",
            binding_references={"database_search.collection_ids": '["bound-collection"]'},
        )
    )

    await knowledge_tools.database_search_result("question", collection_ids=None)

    assert json.loads(requests[0].content)["collection_id"] == "bound-collection"
    assert requests[0].headers["x-user-id"] == "user-1"


async def test_graph_search_uses_only_its_own_collection_binding(rag) -> None:
    requests = rag(_graph_response("graph-collection", "context", "n"))
    set_current_trusted_context(
        TrustedToolContext(
            user_id="user-1",
            binding_references={
                "database_search.collection_ids": '["doc-collection"]',
                "graph_search.collection_ids": '["graph-collection"]',
            },
        )
    )

    await knowledge_tools.graph_search_result("question")

    assert [json.loads(r.content)["collection_id"] for r in requests] == ["graph-collection"]


@pytest.mark.parametrize(
    ("tool", "binding_references"),
    [
        ("graph_search", {"database_search.collection_ids": '["doc-collection"]'}),
        ("database_search", {"graph_search.collection_ids": '["graph-collection"]'}),
        ("database_search", {"connectors.collection_hint": '["stray"]'}),
        ("database_search", {"database_search__collection_ids": '["undecoded"]'}),
    ],
)
async def test_search_never_borrows_another_binding(
    rag, tool: str, binding_references: dict[str, str]
) -> None:
    requests = rag()
    set_current_trusted_context(
        TrustedToolContext(user_id="user-1", binding_references=binding_references)
    )
    search = getattr(knowledge_tools, f"{tool}_result")

    result = await search("question")

    assert json.loads(_text(result))["error_category"] == "validation"
    assert requests == []


async def test_retrieval_failure_hides_internal_details(rag) -> None:
    rag(httpx.ConnectError("connection refused to http://rag-service:8080"))

    result = await knowledge_tools.database_search_result("q", ["col-1"])

    text = _text(result)
    output = json.loads(text)
    assert output["success"] is False
    assert output["error_category"] == "retrieval"
    assert "rag-service" not in text
    assert result.structured_content is None


async def test_unconfigured_rag_service_is_a_configuration_error(monkeypatch) -> None:
    monkeypatch.setattr(knowledge_tools, "build_knowledge_search_service", lambda: None)

    result = await knowledge_tools.graph_search_result("q", ["col-1"])

    assert json.loads(_text(result))["error_category"] == "configuration"


def test_every_knowledge_tool_has_a_model_facing_description() -> None:
    mcp = FastMCP("knowledge-descriptions")
    knowledge_tools.KnowledgeTools().register_tools(mcp)
    (provider,) = mcp.providers
    descriptions = {c.name: c.description for c in provider._components.values()}

    assert set(descriptions) == {"database_search", "document_search", "graph_search"}
    assert all((description or "").strip() for description in descriptions.values())


def test_collection_ids_argument_is_bounded_in_every_knowledge_tool_schema() -> None:
    mcp = FastMCP("knowledge-schema")
    knowledge_tools.KnowledgeTools().register_tools(mcp)
    (provider,) = mcp.providers

    for component in provider._components.values():
        options = component.parameters["properties"]["collection_ids"]["anyOf"]
        array = next(option for option in options if option.get("type") == "array")
        assert array["maxItems"] == MAX_COLLECTION_IDS, component.name
