"""The contract between agent-service and rag-service.

Two production incidents came from this contract being implicit:

* graph search sent ``collection_ids: [x]``; rag-service wants
  ``collection_id: x`` and 422s otherwise (surfaced as "LLM provider error").
* document search returned chunks keyed ``page_content``; every consumer
  read ``content`` — retrieved text was silently dropped.

These tests pin the request shape each route gets and the normalised chunk
shape callers receive, so a rag-service schema change breaks CI here rather
than at runtime.
"""

from __future__ import annotations

import httpx
from error_contract import ApplicationError
import pytest

from integrations import rag_client
from integrations.rag_client import RagChunk


@pytest.fixture
def captured(monkeypatch):
    """Patch the shared transport and record every outgoing request."""
    calls: list[dict] = []

    async def fake_request(
        method, path, *, access_token, params=None, json_body=None, extra_headers=None, **transport
    ):
        calls.append(
            {
                "method": method,
                "path": path,
                "params": params,
                "json": json_body,
                "extra_headers": extra_headers,
                **transport,
            }
        )
        return calls_response["value"]

    calls_response = {"value": []}
    monkeypatch.setattr(rag_client, "_request", fake_request)
    return calls, calls_response


def _stub(monkeypatch, payload):
    """Answer every rag-service call with *payload*, whatever the path."""

    async def fake_request(method, path, *, access_token=None, params=None, json_body=None, **_):
        return payload

    monkeypatch.setattr(rag_client, "_request", fake_request)


@pytest.fixture
def outbound_calls(monkeypatch):
    """Patch ``outbound.request`` itself: what dependency and budget each call uses."""
    from core.http import outbound

    calls: list[dict] = []

    async def fake_outbound(dependency, method, url, *, timeout=None, headers=None, **kwargs):
        calls.append({"dependency": dependency, "method": method, "url": url, "timeout": timeout})
        return httpx.Response(
            200,
            json={"statusCode": 200, "message": "ok", "data": {"chunks_indexed": 0}, "error": None},
            request=httpx.Request(method, url),
        )

    monkeypatch.setattr(outbound, "request", fake_outbound)
    monkeypatch.setenv("INTERNAL_RAG_SERVICE_API_URL", "http://rag")
    return calls


# --- RagChunk normalisation -------------------------------------------------


def test_ragchunk_reads_page_content():
    c = RagChunk.from_wire({"page_content": "the text", "metadata": {"source": "x"}, "score": 0.7})
    assert c.text == "the text"
    assert c.metadata == {"source": "x"}
    assert c.score == 0.7


def test_ragchunk_reads_content_and_text_aliases():
    assert RagChunk.from_wire({"content": "a"}).text == "a"
    assert RagChunk.from_wire({"text": "b"}).text == "b"


def test_ragchunk_prefers_page_content_then_content_then_text():
    c = RagChunk.from_wire({"page_content": "p", "content": "c", "text": "t"})
    assert c.text == "p"


def test_ragchunk_tolerates_missing_text_and_bad_types():
    c = RagChunk.from_wire({"metadata": "not-a-dict", "score": "not-a-number"})
    assert c.text == ""
    assert c.metadata == {}
    assert c.score is None


def test_ragchunk_as_dict_always_has_content_key():
    d = RagChunk.from_wire({"page_content": "x"}).as_dict()
    assert d["content"] == "x"
    assert set(d) == {"content", "metadata", "score"}


# --- search_documents -----------------------------------------------------


@pytest.mark.asyncio
async def test_search_documents_normalises_page_content(captured):
    calls, resp = captured
    resp["value"] = [
        {"page_content": "chunk one", "score": 0.9, "metadata": {"source": "a"}},
        {"page_content": "chunk two", "score": 0.4, "metadata": {"source": "b"}},
    ]
    chunks = await rag_client.search_documents("col-1", "q", top_k=5, access_token="t")
    assert [c.text for c in chunks] == ["chunk one", "chunk two"]
    assert calls[0]["path"] == "/collections/col-1/documents/search"
    assert calls[0]["json"] == {"query": "q", "limit": 5}


@pytest.mark.asyncio
async def test_search_documents_applies_threshold(captured):
    _, resp = captured
    resp["value"] = [
        {"page_content": "keep", "score": 0.8},
        {"page_content": "drop", "score": 0.2},
    ]
    chunks = await rag_client.search_documents("c", "q", threshold=0.5)
    assert [c.text for c in chunks] == ["keep"]


@pytest.mark.asyncio
async def test_search_documents_short_circuits_on_empty_query(captured):
    calls, _ = captured
    assert await rag_client.search_documents("c", "") == []
    assert await rag_client.search_documents("", "q") == []
    assert calls == []


# --- graph search: the collection_id contract ---------------------------


@pytest.mark.asyncio
async def test_search_graph_sends_singular_collection_id(captured):
    calls, resp = captured
    resp["value"] = {"nodes": [], "edges": []}
    await rag_client.search_graph("col-9", "who", limit=15, access_token="t")
    body = calls[0]["json"]
    assert body["collection_id"] == "col-9"
    assert "collection_ids" not in body
    assert body == {"query": "who", "collection_id": "col-9", "limit": 15}
    assert calls[0]["path"] == "/graph/search"


@pytest.mark.asyncio
async def test_graph_entity_search_uses_query_param_q(captured):
    calls, resp = captured
    resp["value"] = {"nodes": [], "edges": []}
    await rag_client.search_graph_entities("c", "türksat", limit=10)
    assert calls[0]["method"] == "GET"
    assert calls[0]["path"] == "/graph/collections/c/search/entities"
    assert calls[0]["params"] == {"q": "türksat", "limit": 10}


@pytest.mark.asyncio
async def test_graph_neighborhood_uses_node_id_param(captured):
    calls, resp = captured
    resp["value"] = {"nodes": [], "edges": []}
    await rag_client.graph_neighborhood("c", "ent-1", depth=2, limit=20)
    assert calls[0]["params"] == {"node_id": "ent-1", "depth": 2, "limit": 20}


# --- datasource ingestion / reads (connector-managed collections) -------


@pytest.mark.asyncio
async def test_ingest_datasource_records_sends_documents_and_clear_flag(captured):
    calls, resp = captured
    resp["value"] = {"chunks_indexed": 3, "chunk_char_total": 30, "chunk_token_total": 8}

    result = await rag_client.ingest_datasource_records(
        "ds-1",
        [{"content": "hello", "metadata": {"stream": "users"}}],
        clear_existing=True,
        access_token="t",
    )

    assert calls[0]["method"] == "POST"
    assert calls[0]["path"] == "/datasources/ds-1/records"
    assert calls[0]["json"] == {
        "documents": [{"content": "hello", "metadata": {"stream": "users"}}],
        "clear_existing": True,
    }
    assert result["chunks_indexed"] == 3


@pytest.mark.asyncio
async def test_ingest_datasource_records_sends_idempotency_key_header(captured):
    calls, resp = captured
    resp["value"] = {"chunks_indexed": 0, "chunk_char_total": 0, "chunk_token_total": 0}

    await rag_client.ingest_datasource_records(
        "ds-1", [], idempotency_key="ingest-batch:ds-1:0"
    )

    assert calls[0]["extra_headers"] == {"Idempotency-Key": "ingest-batch:ds-1:0"}


@pytest.mark.asyncio
async def test_ingest_datasource_records_omits_idempotency_header_when_absent(captured):
    calls, resp = captured
    resp["value"] = {"chunks_indexed": 0, "chunk_char_total": 0, "chunk_token_total": 0}

    await rag_client.ingest_datasource_records("ds-1", [])

    assert calls[0]["extra_headers"] is None


@pytest.mark.asyncio
async def test_ingest_uses_its_own_dependency_and_budget(outbound_calls):
    """A batch is split and embedded inside the request: minutes on a local model.

    Sent under the chat-retrieval dependency it would time out at 15 s, be re-posted by
    the transport retry, and its failures would open the circuit chat retrieval shares.
    """
    from core.http import outbound
    from core.http.rag_http import rag_ingest_timeout_seconds, rag_timeout_seconds

    await rag_client.ingest_datasource_records("ds-1", [{"content": "x", "metadata": {}}])
    await rag_client.search_documents("c", "q")

    ingest, search = outbound_calls
    assert ingest["dependency"] == outbound.RAG_SERVICE_INGEST
    assert ingest["timeout"] == rag_ingest_timeout_seconds() >= 300
    assert search["dependency"] == outbound.RAG_SERVICE
    assert search["timeout"] == rag_timeout_seconds()


@pytest.mark.asyncio
async def test_fetch_datasource_entities_sends_pagination_params(captured):
    calls, resp = captured
    resp["value"] = {"count": 2, "entities": [{"content": "a", "metadata": {}}], "stats": None}

    result = await rag_client.fetch_datasource_entities(
        "ds-1", limit=5, offset=10, include_stats=True
    )

    assert calls[0]["method"] == "GET"
    assert calls[0]["path"] == "/datasources/ds-1/entities"
    assert calls[0]["params"] == {"limit": 5, "offset": 10, "include_stats": True}
    assert result["count"] == 2


@pytest.mark.asyncio
async def test_delete_datasource_records_sends_a_bare_delete(captured):
    calls, resp = captured
    resp["value"] = {"chunks_removed": 12}

    result = await rag_client.delete_datasource_records("ds-1")

    assert calls[0]["method"] == "DELETE"
    assert calls[0]["path"] == "/datasources/ds-1/records"
    assert calls[0]["json"] is None and calls[0]["params"] is None
    assert result == {"chunks_removed": 12}


@pytest.mark.asyncio
async def test_delete_datasource_records_uses_the_ingest_budget(outbound_calls):
    """A Milvus drop, not a chat lookup: the ingest dependency, breaker and timeout."""
    from core.http import outbound
    from core.http.rag_http import rag_ingest_timeout_seconds

    await rag_client.delete_datasource_records("ds-1")

    (call,) = outbound_calls
    assert call["method"] == "DELETE"
    assert call["dependency"] == outbound.RAG_SERVICE_INGEST
    assert call["timeout"] == rag_ingest_timeout_seconds()


# --- transport wiring is exercised end to end --------------------------


@pytest.mark.asyncio
async def test_request_raises_for_status(monkeypatch):
    """The real transport path propagates an error status to the caller."""
    from core.http import outbound

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "statusCode": 422,
                "message": "Field required",
                "data": None,
                "error": {"code": "validation.failed", "message": "Field required"},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(outbound, "get_shared_client", lambda name, **kwargs: client)

    with pytest.raises(ApplicationError) as raised:
        await rag_client.search_graph("c", "q")
    assert raised.value.status_code == 422
    assert raised.value.code == "validation.failed"

    await client.aclose()


# ---------------------------------------------------------------------------
# Collection catalog — the shapes the dropdowns depend on
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collections_read_uuid_and_metadata_name(monkeypatch):
    """rag-service keys the id under ``uuid`` and the label under ``metadata.name``.

    Reading ``id`` instead raised KeyError on every real response and left the
    canvas showing an empty Knowledge Base dropdown.
    """
    cid = "11111111-1111-4111-8111-111111111111"
    _stub(monkeypatch, [{"uuid": cid, "name": "kb_9f3", "metadata": {"name": "Support Docs"}}])

    collections = await rag_client.list_collections(access_token="t")

    assert [(c.id, c.label, c.name) for c in collections] == [(cid, "Support Docs", "kb_9f3")]


@pytest.mark.asyncio
async def test_collections_fall_back_through_id_then_raw_name(monkeypatch):
    """Older responses carry ``id`` and no metadata; they must still resolve."""
    _stub(monkeypatch, [{"id": "c-old", "name": "raw_name_only", "metadata": {}}])

    collections = await rag_client.list_collections()

    assert [(c.id, c.label) for c in collections] == [("c-old", "raw_name_only")]


@pytest.mark.asyncio
async def test_a_row_without_any_id_is_dropped(monkeypatch):
    _stub(monkeypatch, [{"name": "orphan"}, {"uuid": "c-1", "name": "kept"}])

    assert [c.id for c in await rag_client.list_collections()] == ["c-1"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        [{"uuid": "c-1"}],
        {"collections": [{"uuid": "c-1"}]},
        {"collection_ids": ["c-1"]},
    ],
    ids=["bare-list", "collections-key", "collection_ids-key"],
)
async def test_graph_collections_accept_every_shape_the_endpoint_has_returned(
    monkeypatch, payload
):
    """This endpoint has returned objects, a wrapped list and bare ids."""
    _stub(monkeypatch, payload)

    assert [c.id for c in await rag_client.list_graph_collections()] == ["c-1"]


@pytest.mark.asyncio
async def test_a_bare_id_labels_itself_so_the_caller_can_spot_it(monkeypatch):
    """A caller replaces this label from its own name map; it must be detectable."""
    _stub(monkeypatch, {"collection_ids": ["c-1"]})

    collection = (await rag_client.list_graph_collections())[0]

    assert collection.label == collection.id


@pytest.mark.asyncio
async def test_knowledge_sources_carry_the_kind_they_came_from(monkeypatch):
    _stub(
        monkeypatch,
        {
            "document_processing": [{"id": "d-1", "name": "Docs"}],
            "knowledge_graph": [{"id": "g-1"}],
        },
    )

    sources = await rag_client.list_knowledge_sources()

    assert [(s.id, s.label, s.kind) for s in sources] == [
        ("d-1", "Docs", "document_processing"),
        ("g-1", "g-1", "knowledge_graph"),
    ]


@pytest.mark.asyncio
async def test_knowledge_sources_drop_rows_without_an_id(monkeypatch):
    _stub(monkeypatch, {"document_processing": [{"name": "no id"}, {"id": "d-1"}]})

    assert [s.id for s in await rag_client.list_knowledge_sources()] == ["d-1"]


# --- Long-term memory semantic search --------------------------------------
#
# Unlike every other route above, this authenticates via direct
# x-internal-token + x-user-id delegation, not _request()'s Authorization:
# Bearer scheme -- so it's exercised end to end with a mock transport
# rather than through the `captured` fixture.


def _capture_memory_request(monkeypatch, *, payload=None, error=None):
    """Double the shared transport and record the memory-search call."""
    captured: dict = {}

    async def fake_request(
        method, path, *, access_token=None, params=None, json_body=None, extra_headers=None
    ):
        captured.update(
            method=method, path=path, json=json_body, extra_headers=extra_headers or {}
        )
        if error is not None:
            raise error
        return payload

    monkeypatch.setattr(rag_client, "_request", fake_request)
    return captured


@pytest.mark.asyncio
async def test_search_memory_facts_sends_the_delegated_user_and_token(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "shared-secret")
    captured = _capture_memory_request(
        monkeypatch,
        payload={"hits": [{"fact_id": "f1", "content": "User likes tea", "score": 0.9}]},
    )

    hits = await rag_client.search_memory_facts("user-1", "what do I drink", limit=5)

    assert captured["path"] == "/memory/search"
    assert captured["extra_headers"]["x-internal-token"] == "shared-secret"
    assert captured["extra_headers"]["x-user-id"] == "user-1"
    assert hits == [rag_client.MemoryFactHit(fact_id="f1", content="User likes tea", score=0.9)]


@pytest.mark.asyncio
async def test_search_memory_facts_with_a_blank_query_short_circuits(monkeypatch):
    captured = _capture_memory_request(monkeypatch, payload={"hits": []})

    hits = await rag_client.search_memory_facts("user-1", "   ")

    assert hits == []
    assert captured == {}


@pytest.mark.asyncio
async def test_search_memory_facts_fails_open_on_a_server_error(monkeypatch):
    _capture_memory_request(monkeypatch, error=httpx.HTTPStatusError(
        "boom", request=httpx.Request("POST", "http://rag/memory/search"),
        response=httpx.Response(500),
    ))

    assert await rag_client.search_memory_facts("user-1", "anything") == []


@pytest.mark.asyncio
async def test_search_memory_facts_fails_open_on_a_transport_error(monkeypatch):
    _capture_memory_request(monkeypatch, error=httpx.ConnectError("connection refused"))

    assert await rag_client.search_memory_facts("user-1", "anything") == []


@pytest.mark.asyncio
async def test_search_memory_facts_skips_malformed_hits(monkeypatch):
    _capture_memory_request(
        monkeypatch,
        payload={"hits": [
            {"fact_id": "f1", "content": "kept", "score": 0.5},
            "not-a-dict",
        ]},
    )

    hits = await rag_client.search_memory_facts("user-1", "anything")

    assert hits == [rag_client.MemoryFactHit(fact_id="f1", content="kept", score=0.5)]
