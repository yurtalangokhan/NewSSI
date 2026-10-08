"""Tests for ``ExpansionRepository`` — previously untested drill-down logic.

``build_sub_clusters`` is pure and tested directly. The async paths use the
established ``_session`` monkeypatch pattern (see
``test_entity_bulk_upsert_batching.py``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest

from src.graph.repositories.expansion_repository import ExpansionRepository


class _FakeResult:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._records = records

    def __aiter__(self) -> AsyncIterator[dict[str, Any]]:
        return self._iter()

    async def _iter(self):
        for record in self._records:
            yield record

    async def single(self) -> dict[str, Any] | None:
        return self._records[0] if self._records else None


class _FakeSession:
    def __init__(self, results_by_call: list[list[dict[str, Any]]]) -> None:
        self._results_by_call = list(results_by_call)
        self.calls: list[tuple[Any, dict[str, Any]]] = []

    async def run(self, query: Any, **params: Any) -> _FakeResult:
        self.calls.append((query, params))
        records = self._results_by_call.pop(0) if self._results_by_call else []
        return _FakeResult(records)


def _repo(monkeypatch, results_by_call: list[list[dict[str, Any]]]):
    session = _FakeSession(results_by_call)

    @asynccontextmanager
    async def _session(self: ExpansionRepository, **_kwargs: Any):
        yield session

    monkeypatch.setattr(ExpansionRepository, "_session", _session)
    return ExpansionRepository("col-1"), session


# ---------------------------------------------------------------------------
# build_sub_clusters — pure static method
# ---------------------------------------------------------------------------


def test_build_sub_clusters_splits_into_even_chunks():
    clusters = ExpansionRepository.build_sub_clusters("Person", 250, 100)
    assert [c.node_count for c in clusters] == [100, 100, 50]
    assert [c.id for c in clusters] == [
        "subcluster__Person__0__100",
        "subcluster__Person__100__100",
        "subcluster__Person__200__100",
    ]


def test_build_sub_clusters_names_are_1_indexed_and_show_size():
    clusters = ExpansionRepository.build_sub_clusters("Person", 250, 100)
    assert clusters[0].name == "Person #1 (100)"
    assert clusters[2].name == "Person #3 (50)"


def test_build_sub_clusters_slices_top_entities_per_chunk():
    names = [f"n{i}" for i in range(250)]
    clusters = ExpansionRepository.build_sub_clusters(
        "Person", 250, 100, top_entities_per_chunk=3, entity_names=names
    )
    assert clusters[0].top_entities == ["n0", "n1", "n2"]
    assert clusters[1].top_entities == ["n100", "n101", "n102"]


def test_build_sub_clusters_without_entity_names_has_no_top_entities():
    clusters = ExpansionRepository.build_sub_clusters("Person", 100, 50)
    assert all(c.top_entities == [] for c in clusters)


def test_build_sub_clusters_records_skip_and_limit_in_properties():
    clusters = ExpansionRepository.build_sub_clusters("Person", 250, 100)
    assert clusters[1].properties == {"_skip": 100, "_limit": 100}


def test_build_sub_clusters_empty_for_zero_total():
    assert ExpansionRepository.build_sub_clusters("Person", 0, 100) == []


# ---------------------------------------------------------------------------
# expand_cluster
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expand_cluster_returns_empty_when_no_nodes_match(monkeypatch):
    repo, session = _repo(monkeypatch, [[]])
    data = await repo.expand_cluster("Ghost")
    assert data.nodes == []
    assert data.edges == []
    # No edge query fired since there were no node ids to look edges up for.
    assert len(session.calls) == 1


@pytest.mark.asyncio
async def test_expand_cluster_fetches_edges_only_between_matched_nodes(monkeypatch):
    nodes = [{"id": "n1", "label": "Person", "name": "Alice", "props": {}}]
    edges = [{"id": "e1", "src": "n1", "tgt": "n1", "rtype": "SELF", "props": {}}]
    repo, session = _repo(monkeypatch, [nodes, edges])

    data = await repo.expand_cluster("Person", node_limit=10, edge_limit=20)

    assert len(data.nodes) == 1
    assert len(data.edges) == 1
    _, edge_params = session.calls[1]
    assert edge_params["ids"] == ["n1"]
    assert edge_params["elimit"] == 20


# ---------------------------------------------------------------------------
# expand_cluster_slice
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expand_cluster_slice_passes_skip_and_limit(monkeypatch):
    repo, session = _repo(monkeypatch, [[]])
    await repo.expand_cluster_slice("Person", skip=100, limit=50)
    _, params = session.calls[0]
    assert params["skip"] == 100
    assert params["limit"] == 50


# ---------------------------------------------------------------------------
# get_neighborhood
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_neighborhood_returns_empty_for_unknown_node(monkeypatch):
    repo, session = _repo(monkeypatch, [[]])
    data = await repo.get_neighborhood("missing")
    assert data.nodes == []
    assert data.edges == []


@pytest.mark.asyncio
async def test_get_neighborhood_fetches_edges_with_high_ceiling(monkeypatch):
    nodes = [{"id": "n1", "label": "Person", "name": "Alice", "props": {}}]
    edges = []
    repo, session = _repo(monkeypatch, [nodes, edges])

    await repo.get_neighborhood("n1", depth=2, limit=50)

    _, edge_params = session.calls[1]
    assert edge_params["elimit"] == 10_000


# ---------------------------------------------------------------------------
# get_important_nodes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_important_nodes_injects_degree_into_properties(monkeypatch):
    records = [
        {"id": "n1", "label": "Person", "name": "Alice", "props": {}, "degree": 7},
    ]
    repo, session = _repo(monkeypatch, [records])

    nodes = await repo.get_important_nodes(limit=10)

    assert nodes[0].properties["degree"] == 7


# ---------------------------------------------------------------------------
# Label metadata helpers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_count_label_nodes_returns_zero_when_no_record(monkeypatch):
    repo, session = _repo(monkeypatch, [[]])
    assert await repo.count_label_nodes("Ghost") == 0


@pytest.mark.asyncio
async def test_count_label_nodes_returns_the_count(monkeypatch):
    repo, session = _repo(monkeypatch, [[{"cnt": 42}]])
    assert await repo.count_label_nodes("Person") == 42


@pytest.mark.asyncio
async def test_count_label_edges_returns_the_count(monkeypatch):
    repo, session = _repo(monkeypatch, [[{"cnt": 17}]])
    assert await repo.count_label_edges("Person") == 17


@pytest.mark.asyncio
async def test_get_label_metadata_defaults_missing_label_to_entity(monkeypatch):
    rel_records = [{"rtype": "WORKS_AT", "cnt": 5}]
    label_records = [{"blabel": None, "cnt": 2}]
    repo, session = _repo(monkeypatch, [rel_records, label_records])

    rel_counts, neighbor_counts = await repo.get_label_metadata("Person")

    assert rel_counts == {"WORKS_AT": 5}
    assert neighbor_counts == {"Entity": 2}


@pytest.mark.asyncio
async def test_top_entity_names_returns_names_in_order(monkeypatch):
    records = [{"name": "Alice"}, {"name": "Bob"}]
    repo, session = _repo(monkeypatch, [records])

    names = await repo.top_entity_names("Person", limit=10)

    assert names == ["Alice", "Bob"]


@pytest.mark.asyncio
async def test_get_chunked_internal_rel_types_groups_by_offset(monkeypatch):
    records = [
        {"offset": 0, "rtype": "KNOWS", "cnt": 3},
        {"offset": 0, "rtype": "WORKS_WITH", "cnt": 1},
        {"offset": 100, "rtype": "KNOWS", "cnt": 2},
    ]
    repo, session = _repo(monkeypatch, [records])

    result = await repo.get_chunked_internal_rel_types("Person", chunk_size=100)

    assert result == {
        0: {"KNOWS": 3, "WORKS_WITH": 1},
        100: {"KNOWS": 2},
    }
