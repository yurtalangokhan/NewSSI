"""``DatasourceRepository``'s Milvus-backed reads now go through rag-service.

These used to open a Milvus connection directly (duplicated connection code
also present in rag-service, and a real risk of the two services picking
different embedding models for the same collection). They now call
``integrations.rag_client.fetch_datasource_entities`` instead.
"""

from __future__ import annotations

import pytest
from error_contract import DependencyUnavailableError

from infrastructure.db.repositories import datasource_repo as repo_module
from infrastructure.db.repositories.datasource_repo import DatasourceRepository


@pytest.mark.asyncio
async def test_count_embeddings_reads_count_from_rag_service(monkeypatch):
    async def fake_fetch(collection_id, *, limit=10, offset=0, include_stats=False, access_token=None):
        assert collection_id == "ds-1"
        assert limit == 0
        return {"count": 42, "entities": [], "stats": None}

    monkeypatch.setattr(repo_module, "fetch_datasource_entities", fake_fetch)

    count = await DatasourceRepository().count_embeddings("ds-1")

    assert count == 42


@pytest.mark.asyncio
async def test_count_embeddings_propagates_rag_service_unavailability(monkeypatch):
    async def fake_fetch(*args, **kwargs):
        raise DependencyUnavailableError()

    monkeypatch.setattr(repo_module, "fetch_datasource_entities", fake_fetch)

    with pytest.raises(DependencyUnavailableError):
        await DatasourceRepository().count_embeddings("ds-1")


@pytest.mark.asyncio
async def test_get_paginated_embeddings_maps_content_and_metadata(monkeypatch):
    async def fake_fetch(collection_id, *, limit=10, offset=0, include_stats=False, access_token=None):
        assert collection_id == "ds-1"
        assert limit == 5
        assert offset == 10
        return {
            "count": 1,
            "entities": [{"content": "hello world", "metadata": {"stream": "users"}}],
            "stats": None,
        }

    monkeypatch.setattr(repo_module, "fetch_datasource_entities", fake_fetch)

    rows = await DatasourceRepository().get_paginated_embeddings("ds-1", limit=5, offset=10)

    assert rows == [{"document": "hello world", "cmetadata": {"stream": "users"}}]


@pytest.mark.asyncio
async def test_get_paginated_embeddings_propagates_rag_service_unavailability(
    monkeypatch,
):
    async def fake_fetch(*args, **kwargs):
        raise DependencyUnavailableError()

    monkeypatch.setattr(repo_module, "fetch_datasource_entities", fake_fetch)

    with pytest.raises(DependencyUnavailableError):
        await DatasourceRepository().get_paginated_embeddings("ds-1")
