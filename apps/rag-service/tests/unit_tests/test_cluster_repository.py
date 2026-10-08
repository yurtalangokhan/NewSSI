"""Tests for ``ClusterRepository`` — previously untested clustering logic.

``_build_clustered_response`` is pure and tested directly. The async paths
use the established ``_session`` monkeypatch pattern (see
``test_entity_bulk_upsert_batching.py``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock

import pytest
from neo4j.exceptions import ClientError

from src.graph.repositories.cluster_repository import ClusterRepository
from src.graph.schemas import ClusterNode, GraphNode, GraphStats
from src.shared.errors import database_errors


class _FakeResult:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._records = records

    def __aiter__(self) -> AsyncIterator[dict[str, Any]]:
        return self._iter()

    async def _iter(self):
        for record in self._records:
            yield record


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
    async def _session(self: ClusterRepository, **_kwargs: Any):
        yield session

    monkeypatch.setattr(ClusterRepository, "_session", _session)
    repo = ClusterRepository("col-1")
    return repo, session


def _stats(node_count: int = 1000, edge_count: int = 2000) -> GraphStats:
    return GraphStats(collection_id="col-1", node_count=node_count, edge_count=edge_count)


# ---------------------------------------------------------------------------
# _build_clustered_response — pure, no Neo4j needed
# ---------------------------------------------------------------------------


def test_single_member_community_becomes_a_plain_node():
    communities = {0: [{"id": "n1", "name": "Alice", "label": "Person"}]}
    result = ClusterRepository._build_clustered_response(
        communities=communities,
        max_clusters=10,
        top_entities_per_cluster=5,
        stats=_stats(),
    )
    assert len(result.nodes) == 1
    assert isinstance(result.nodes[0], GraphNode)
    assert result.nodes[0].name == "Alice"
    assert result.cluster_count == 0


def test_multi_member_community_becomes_a_cluster_node():
    communities = {
        0: [
            {"id": "n1", "name": "Alice", "label": "Person"},
            {"id": "n2", "name": "Bob", "label": "Person"},
        ]
    }
    result = ClusterRepository._build_clustered_response(
        communities=communities,
        max_clusters=10,
        top_entities_per_cluster=5,
        stats=_stats(),
    )
    assert len(result.nodes) == 1
    node = result.nodes[0]
    assert isinstance(node, ClusterNode)
    assert node.node_count == 2
    assert node.is_cluster is True
    assert node.name == "Person (2)"
    assert result.cluster_count == 1


def test_communities_are_merged_by_dominant_label_before_truncation():
    """Two separate raw communities that share a dominant label merge into
    one cluster -- every node must still be counted even though the merged
    result is later capped to max_clusters.
    """
    communities = {
        0: [{"id": "n1", "name": "Alice", "label": "Person"}] * 1,
        1: [{"id": "n2", "name": "Bob", "label": "Person"}] * 1,
    }
    result = ClusterRepository._build_clustered_response(
        communities=communities,
        max_clusters=10,
        top_entities_per_cluster=5,
        stats=_stats(node_count=2, edge_count=0),
    )
    # Both raw communities were single-label "Person" and get merged into
    # one dominant-label group of 2 -> one ClusterNode, not two nodes.
    assert len(result.nodes) == 1
    assert result.nodes[0].node_count == 2


def test_truncation_keeps_the_largest_clusters_first():
    communities = {
        0: [{"id": f"a{i}", "name": f"a{i}", "label": "Small"} for i in range(2)],
        1: [{"id": f"b{i}", "name": f"b{i}", "label": "Big"} for i in range(5)],
    }
    result = ClusterRepository._build_clustered_response(
        communities=communities,
        max_clusters=1,
        top_entities_per_cluster=5,
        stats=_stats(node_count=7, edge_count=0),
    )
    assert len(result.nodes) == 1
    assert result.nodes[0].label == "Big"


def test_top_entities_are_capped_per_cluster():
    communities = {
        0: [{"id": f"n{i}", "name": f"n{i}", "label": "Person"} for i in range(10)]
    }
    result = ClusterRepository._build_clustered_response(
        communities=communities,
        max_clusters=10,
        top_entities_per_cluster=3,
        stats=_stats(node_count=10, edge_count=0),
    )
    assert len(result.nodes[0].top_entities) == 3


def test_total_counts_come_from_stats_not_from_the_sample():
    communities = {0: [{"id": "n1", "name": "Alice", "label": "Person"}]}
    result = ClusterRepository._build_clustered_response(
        communities=communities,
        max_clusters=10,
        top_entities_per_cluster=5,
        stats=_stats(node_count=99999, edge_count=88888),
    )
    assert result.total_node_count == 99999
    assert result.total_edge_count == 88888


# ---------------------------------------------------------------------------
# get_graph_overview — mode selection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_small_graph_returns_full_mode_without_clustering(monkeypatch):
    repo, session = _repo(monkeypatch, [])
    repo._stats_repo = AsyncMock(
        get_stats=AsyncMock(return_value=_stats(node_count=5, edge_count=5))
    )

    from src.graph.repositories import entity_repository as entity_module

    fake_data = GraphNode(id="n1", label="Person", name="Alice", properties={})

    async def fake_get_graph_data(self, *, node_limit, edge_limit):
        from src.graph.schemas import GraphData

        return GraphData(nodes=[fake_data], edges=[])

    monkeypatch.setattr(
        entity_module.EntityRepository, "get_graph_data", fake_get_graph_data
    )

    result = await repo.get_graph_overview(max_clusters=200)

    assert result.mode == "full"
    assert result.nodes == [fake_data]
    assert session.calls == []  # no clustering query was ever run


@pytest.mark.asyncio
async def test_large_graph_falls_back_to_label_clustering_when_louvain_fails(
    monkeypatch,
):
    """GDS may not be installed/licensed on every Neo4j deployment -- a
    Louvain failure must degrade to the label-based fallback, not blow up
    the whole overview request.
    """
    records = [
        {"id": "n1", "name": "Alice", "label": "Person", "degree": 3},
        {"id": "n2", "name": "Bob", "label": "Person", "degree": 1},
    ]

    calls = {"n": 0}

    class _FailingThenLabelSession(_FakeSession):
        async def run(self, query, **params):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ClientError("GDS not available")
            return await super().run(query, **params)

    session = _FailingThenLabelSession([records])

    @asynccontextmanager
    async def _session(self, **_kwargs):
        # The real session maps driver failures to typed database errors.
        with database_errors():
            yield session

    monkeypatch.setattr(ClusterRepository, "_session", _session)
    repo = ClusterRepository("col-1")
    repo._stats_repo = AsyncMock(
        get_stats=AsyncMock(return_value=_stats(node_count=1000, edge_count=2000))
    )

    result = await repo.get_graph_overview(max_clusters=200)

    assert result.mode == "overview"
    assert len(result.nodes) == 1
    assert result.nodes[0].node_count == 2
