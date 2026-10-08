"""``DatasourceService.list_datasources``'s Milvus fallback count.

It used to batch-query pymilvus directly, keyed by collection *name*
(``_count_milvus_entities_batch``). That function is gone along with the
rest of agent-service's direct Milvus access -- this now asks each
datasource's own repository method (which calls rag-service) concurrently,
keyed by *id*.
"""

from __future__ import annotations

import pytest

from service.datasources.datasource_service import DatasourceService


class _FakeDatasources:
    def __init__(self, rows):
        self._rows = rows
        self.counted_ids: list[str] = []

    async def list_datasource_collections(self):
        return self._rows

    async def count_embeddings(self, datasource_id: str) -> int:
        self.counted_ids.append(datasource_id)
        return {"ds-needs-count": 7}.get(datasource_id, 0)


class _NoRows:
    """Stands in for the connection and schedule repositories."""

    async def list_all(self):
        return []


@pytest.mark.asyncio
async def test_list_datasources_counts_only_rows_missing_precomputed_stats(monkeypatch):
    rows = [
        {
            "uuid": "ds-has-stats",
            "name": "has-stats",
            "cmetadata": {"chunk_stats": {"chunk_count": 3}},
            "doc_count": 0,
        },
        {
            "uuid": "ds-needs-count",
            "name": "needs-count",
            "cmetadata": {},
            "doc_count": 0,
        },
    ]
    fake_repo = _FakeDatasources(rows)
    controller = DatasourceService(ds_repo=fake_repo, connection_repo=_NoRows(), schedule_repo=_NoRows())

    results = await controller.list_datasources()

    # Only the row without precomputed stats triggers a rag-service call.
    assert fake_repo.counted_ids == ["ds-needs-count"]

    by_id = {r["id"]: r for r in results}
    assert by_id["ds-has-stats"]["document_count"] == 3
    assert by_id["ds-needs-count"]["document_count"] == 7


@pytest.mark.asyncio
async def test_list_datasources_returns_empty_list_for_no_rows():
    fake_repo = _FakeDatasources([])
    controller = DatasourceService(ds_repo=fake_repo)

    assert await controller.list_datasources() == []
