"""API-level tests for the connector-managed datasource ingestion/read routes.

``Collection``'s Milvus calls are monkeypatched at the class level (the same
way ``test_knowledge_selector_omits_orphan_graph_collections`` patches
``GraphStore``) so these exercise routing, auth and request/response shape
without needing a live Milvus -- the Milvus-facing logic itself is covered
by ``test_collection_datasource_entities.py``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.shared.authorization import AuthorizationClient
from tests.unit_tests.fixtures import get_async_test_client

INTERNAL_HEADERS = {
    "X-Internal-Service-Token": "internal-token",
}

RECORD_KEY_A = "a" * 40
RECORD_KEY_B = "b" * 40


@pytest.fixture(autouse=True)
def isolate_resource_permissions(monkeypatch):
    monkeypatch.setattr("src.shared.auth.INTERNAL_SERVICE_TOKEN", "internal-token")
    # Gateway authenticates callers now; rag-service no longer looks a user up
    # from a bearer token, so there is nothing to stub on that path.
    monkeypatch.setattr(
        AuthorizationClient, "get_user_accessible_collections", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        AuthorizationClient,
        "check_collection_access",
        AsyncMock(return_value={"allowed": False}),
    )


def idempotency_headers(base_headers: dict[str, str], key: str) -> dict[str, str]:
    return {**base_headers, "Idempotency-Key": key}


async def _create_connector_managed_collection(client) -> str:
    resp = await client.post(
        "/api/v1/collections",
        json={"name": "ds_records_test", "metadata": {"connector_type": "postgres"}},
        headers=idempotency_headers(INTERNAL_HEADERS, "ds-records-col"),
    )
    assert resp.status_code == 201
    return resp.json()["uuid"]


async def test_ingest_datasource_records_chunks_embeds_and_reports_totals(
    monkeypatch,
) -> None:
    upserted: list[list[Any]] = []

    async def fake_upsert(self, documents):
        upserted.append(documents)
        return [str(i) for i in range(len(documents))]

    from src.documents.service import Collection

    monkeypatch.setattr(Collection, "upsert", fake_upsert)

    async with get_async_test_client() as client:
        collection_id = await _create_connector_managed_collection(client)

        resp = await client.post(
            f"/api/v1/datasources/{collection_id}/records",
            json={
                "documents": [{"content": "hello world", "metadata": {"stream": "users"}}],
                "clear_existing": False,
            },
            headers=idempotency_headers(INTERNAL_HEADERS, "ds-records-ingest-1"),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["chunks_indexed"] == 1
        assert body["chunk_char_total"] == len("hello world")
        assert upserted
        assert upserted[0][0].page_content == "hello world"


async def test_ingest_datasource_records_clears_existing_first(monkeypatch) -> None:
    calls: list[str] = []

    from src.documents.service import Collection

    async def fake_clear(self):
        calls.append("clear")
        return 3

    async def fake_upsert(self, documents):
        calls.append("upsert")
        return ["1"]

    monkeypatch.setattr(Collection, "clear", fake_clear)
    monkeypatch.setattr(Collection, "upsert", fake_upsert)

    async with get_async_test_client() as client:
        collection_id = await _create_connector_managed_collection(client)

        resp = await client.post(
            f"/api/v1/datasources/{collection_id}/records",
            json={"documents": [{"content": "x", "metadata": {}}], "clear_existing": True},
            headers=idempotency_headers(INTERNAL_HEADERS, "ds-records-ingest-2"),
        )

        assert resp.status_code == 200
        assert calls == ["clear", "upsert"]


async def test_ingest_datasource_records_with_no_documents_is_a_noop(monkeypatch) -> None:
    from src.documents.service import Collection

    async def fail_upsert(self, documents):
        raise AssertionError("must not upsert an empty batch")

    monkeypatch.setattr(Collection, "upsert", fail_upsert)

    async with get_async_test_client() as client:
        collection_id = await _create_connector_managed_collection(client)

        resp = await client.post(
            f"/api/v1/datasources/{collection_id}/records",
            json={"documents": []},
            headers=idempotency_headers(INTERNAL_HEADERS, "ds-records-ingest-3"),
        )

        assert resp.status_code == 200
        assert resp.json() == {
            "chunks_indexed": 0,
            "chunk_char_total": 0,
            "chunk_token_total": 0,
            "chunks_replaced": 0,
        }


def _records_url() -> str:
    """The records route of a collection that is never looked up.

    The tests below patch every ``Collection`` method the route calls, so the
    collection needs no row in PostgreSQL and any id will do.
    """
    return f"/api/v1/datasources/{uuid4()}/records"


def _patch_writes(monkeypatch) -> dict[str, list[Any]]:
    """Record what the route hands to ``upsert`` and ``replace_records``."""
    from src.documents.service import Collection

    calls: dict[str, list[Any]] = {"upsert": [], "replace_records": []}

    async def fake_upsert(self, documents):
        calls["upsert"].append(documents)
        return [str(i) for i in range(len(documents))]

    async def fake_replace_records(self, record_keys, documents):
        calls["replace_records"].append((record_keys, documents))
        return 3

    monkeypatch.setattr(Collection, "upsert", fake_upsert)
    monkeypatch.setattr(Collection, "replace_records", fake_replace_records)
    return calls


async def test_ingest_keyed_records_replaces_what_was_stored_for_them(
    monkeypatch,
) -> None:
    calls = _patch_writes(monkeypatch)
    long_text = " ".join(["word"] * 600)

    async with get_async_test_client() as client:
        resp = await client.post(
            _records_url(),
            json={
                "documents": [
                    {
                        "content": long_text,
                        "metadata": {"stream": "users"},
                        "record_key": RECORD_KEY_A,
                    },
                    {
                        "content": "second",
                        "metadata": {"stream": "users", "_record_key": "from-source"},
                        "record_key": RECORD_KEY_B,
                    },
                ]
            },
            headers=idempotency_headers(INTERNAL_HEADERS, "ds-records-keyed-1"),
        )

    assert resp.status_code == 200
    assert calls["upsert"] == []
    record_keys, chunks = calls["replace_records"][0]
    assert record_keys == [RECORD_KEY_A, RECORD_KEY_B]
    # Every chunk of a record carries its key, whatever the source sent there.
    assert len(chunks) > 2
    assert [c.metadata["_record_key"] for c in chunks] == [
        *[RECORD_KEY_A] * (len(chunks) - 1),
        RECORD_KEY_B,
    ]
    body = resp.json()
    assert body["chunks_indexed"] == len(chunks)
    assert body["chunks_replaced"] == 3


async def test_ingest_keeps_the_last_document_of_a_repeated_record_key(
    monkeypatch,
) -> None:
    calls = _patch_writes(monkeypatch)

    async with get_async_test_client() as client:
        resp = await client.post(
            _records_url(),
            json={
                "documents": [
                    {"content": "old version", "record_key": RECORD_KEY_A},
                    {"content": "another record", "record_key": RECORD_KEY_B},
                    {"content": "new version", "record_key": RECORD_KEY_A},
                ]
            },
            headers=idempotency_headers(INTERNAL_HEADERS, "ds-records-keyed-2"),
        )

    assert resp.status_code == 200
    record_keys, chunks = calls["replace_records"][0]
    assert sorted(record_keys) == [RECORD_KEY_A, RECORD_KEY_B]
    assert [c.page_content for c in chunks] == ["another record", "new version"]
    assert resp.json()["chunks_indexed"] == 2


async def test_ingest_without_record_keys_appends(monkeypatch) -> None:
    calls = _patch_writes(monkeypatch)

    async with get_async_test_client() as client:
        resp = await client.post(
            _records_url(),
            json={"documents": [{"content": "hello world", "metadata": {}}]},
            headers=idempotency_headers(INTERNAL_HEADERS, "ds-records-keyed-3"),
        )

    assert resp.status_code == 200
    assert calls["replace_records"] == []
    assert "_record_key" not in calls["upsert"][0][0].metadata
    assert resp.json() == {
        "chunks_indexed": 1,
        "chunk_char_total": len("hello world"),
        "chunk_token_total": 2,
        "chunks_replaced": 0,
    }


async def test_ingest_stores_keyed_and_unkeyed_documents_in_one_write(
    monkeypatch,
) -> None:
    calls = _patch_writes(monkeypatch)

    async with get_async_test_client() as client:
        resp = await client.post(
            _records_url(),
            json={
                "documents": [
                    {"content": "keyed", "record_key": RECORD_KEY_A},
                    {"content": "unkeyed"},
                ]
            },
            headers=idempotency_headers(INTERNAL_HEADERS, "ds-records-keyed-4"),
        )

    assert resp.status_code == 200
    assert calls["upsert"] == []
    record_keys, chunks = calls["replace_records"][0]
    assert record_keys == [RECORD_KEY_A]
    assert [c.page_content for c in chunks] == ["keyed", "unkeyed"]


@pytest.mark.parametrize("record_key", ["abc", "A" * 40, "g" * 40, "a" * 41, ""])
async def test_ingest_rejects_a_record_key_that_is_not_a_sha1(
    monkeypatch, record_key
) -> None:
    calls = _patch_writes(monkeypatch)

    async with get_async_test_client() as client:
        resp = await client.post(
            _records_url(),
            json={"documents": [{"content": "x", "record_key": record_key}]},
            headers=idempotency_headers(
                INTERNAL_HEADERS,
                f"ds-records-keyed-5-{len(record_key)}-{record_key[:1]}",
            ),
        )

    assert resp.status_code == 422
    assert calls == {"upsert": [], "replace_records": []}


async def test_retire_runs_keeps_the_named_job_and_reports_what_went(monkeypatch) -> None:
    # The end of an overwrite sync: the previous version stayed searchable while the
    # run landed; now every chunk the run did not write goes.
    from src.documents.service import Collection

    kept: list[str] = []

    async def fake_retire(self, keep_job_id):
        kept.append(keep_job_id)
        return 42

    monkeypatch.setattr(Collection, "retire_other_runs", fake_retire)

    async with get_async_test_client() as client:
        resp = await client.post(
            f"/api/v1/datasources/{uuid4()}/records/retire",
            json={"keep_job_id": "job-7"},
            headers=INTERNAL_HEADERS,  # no idempotency key needed
        )

    assert resp.status_code == 200
    assert resp.json() == {"chunks_removed": 42} and kept == ["job-7"]


@pytest.mark.parametrize("keep_job_id", ["", "job 7", 'x" or 1 == 1', "a" * 129])
async def test_retire_runs_rejects_a_job_id_that_cannot_go_into_a_filter(
    monkeypatch, keep_job_id
) -> None:
    from src.documents.service import Collection

    async def fail_retire(self, keep_job_id):
        raise AssertionError("must not reach Milvus")

    monkeypatch.setattr(Collection, "retire_other_runs", fail_retire)

    async with get_async_test_client() as client:
        resp = await client.post(
            f"/api/v1/datasources/{uuid4()}/records/retire",
            json={"keep_job_id": keep_job_id},
            headers=INTERNAL_HEADERS,
        )

    assert resp.status_code == 422


async def test_delete_records_drops_the_table_and_reports_what_it_held(monkeypatch) -> None:
    # agent-service deletes a datasource: what rag-service stored for it goes first.
    from src.documents.service import Collection

    dropped: list[str] = []

    async def fake_drop(self):
        dropped.append(self.collection_id)
        return 7

    monkeypatch.setattr(Collection, "drop", fake_drop)
    collection_id = uuid4()

    async with get_async_test_client() as client:
        resp = await client.delete(
            f"/api/v1/datasources/{collection_id}/records", headers=INTERNAL_HEADERS
        )

    assert resp.status_code == 200
    assert resp.json() == {"chunks_removed": 7} and dropped == [str(collection_id)]


async def test_list_datasource_entities_returns_count_and_page(monkeypatch) -> None:
    from src.documents.service import Collection

    async def fake_entity_count(self):
        return 9

    async def fake_list_raw_entities(self, *, limit, offset):
        assert limit == 2
        assert offset == 1
        return [{"content": "row", "metadata": {"stream": "users"}}]

    monkeypatch.setattr(Collection, "entity_count", fake_entity_count)
    monkeypatch.setattr(Collection, "list_raw_entities", fake_list_raw_entities)

    async with get_async_test_client() as client:
        collection_id = await _create_connector_managed_collection(client)

        resp = await client.get(
            f"/api/v1/datasources/{collection_id}/entities",
            params={"limit": 2, "offset": 1},
            headers=INTERNAL_HEADERS,
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 9
        assert body["entities"] == [{"content": "row", "metadata": {"stream": "users"}}]
        assert body["stats"] is None


async def test_list_datasource_entities_includes_stats_when_requested(monkeypatch) -> None:
    from src.documents.service import Collection

    async def fake_entity_count(self):
        return 1

    async def fake_list_raw_entities(self, *, limit, offset):
        return []

    async def fake_entity_stats(self):
        return {"chunk_count": 1, "avg_chunk_chars": 10, "avg_chunk_tokens": 3}

    monkeypatch.setattr(Collection, "entity_count", fake_entity_count)
    monkeypatch.setattr(Collection, "list_raw_entities", fake_list_raw_entities)
    monkeypatch.setattr(Collection, "entity_stats", fake_entity_stats)

    async with get_async_test_client() as client:
        collection_id = await _create_connector_managed_collection(client)

        resp = await client.get(
            f"/api/v1/datasources/{collection_id}/entities",
            params={"include_stats": True},
            headers=INTERNAL_HEADERS,
        )

        assert resp.status_code == 200
        assert resp.json()["stats"] == {
            "chunk_count": 1,
            "avg_chunk_chars": 10,
            "avg_chunk_tokens": 3,
        }
